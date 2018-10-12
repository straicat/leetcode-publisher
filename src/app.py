import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime

import yaml
from jinja2 import Template
from requests import HTTPError

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from leetcode import UserCN, UserEN

PREFIX = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


class UserCNSP(UserCN):
    def __init__(self):
        super().__init__()

    def request(self, method, url, **kwargs):
        for _ in range(3):
            try:
                return super().request(method, url, **kwargs)
            except HTTPError:
                for t in range(60, 0, -1):  # Error 429 - Rate limit exceeded!
                    print('\rWait for %d seconds...    ' % t, end='', flush=True)
                    time.sleep(1)
                print()


class UserENSP(UserEN):
    def __init__(self):
        super().__init__()

    def request(self, method, url, **kwargs):
        for _ in range(3):
            try:
                return super().request(method, url, **kwargs)
            except HTTPError:
                for t in range(60, 0, -1):  # Error 429 - Rate limit exceeded!
                    print('\rWait for %d seconds...    ' % t, end='', flush=True)
                    time.sleep(1)
                print()


class RepoGen:
    def __init__(self, conf):
        self.conf = conf
        self.user = None
        self.all_submissions = []
        self.ac_submissions = defaultdict(list)
        self.solutions = {}
        self.questions = {}
        self.notes = {}
        self.likes = {}

    def main(self):
        self.logger()
        if self.login():
            print('> Login successful!')
            self.prepare_submissions()
            self.prepare_solutions()
            self.prepare_questions()
            self.prepare_notes()
            self.prepare_likes()
            self.prepare_render()
            self.render_readme()
            self.render_problems()
            self.copy_source()
            self.deploy()
        else:
            print('> Login failed!')

    @staticmethod
    def logger():
        log_file = os.path.join(PREFIX, '_cache', 'log', '%s.log' % datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s | %(message)s'))
        root.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        root.addHandler(sh)

    def login(self):
        domain = self.conf['account']['domain']
        if domain == 'cn':
            self.user = UserCNSP()
        elif domain == 'en':
            self.user = UserENSP()
        return self.user.login(self.conf['account']['user'], self.conf['account']['password'])

    def __submissions(self):
        sub_file = os.path.join(PREFIX, '_cache', 'submissions.json')
        if os.path.exists(sub_file):
            with open(sub_file, 'r', encoding='utf-8') as f:
                self.all_submissions = json.load(f)
        stored_submission_ids = set([sd['id'] for sd in self.all_submissions])
        has_next = True
        stop_flag = False
        page = 0
        while has_next and not stop_flag:
            page += 1
            print('\r> Get submission record of page %d      ' % page, end='', flush=True)
            j = self.user.submissions(page)
            has_next = j['has_next']
            for sd in j['submissions_dump']:
                if sd['id'] in stored_submission_ids:
                    stop_flag = True
                    break
                self.all_submissions.insert(0, sd)
                yield sd
        print('\r> Get submission record completed!            ')

        with open(sub_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_submissions, f)

    def prepare_submissions(self):
        for sd in self.__submissions():
            if sd['status_display'] != 'Accepted':
                continue
            if sd['title'] in self.ac_submissions:
                if sd['lang'] in [sub['lang'] for sub in self.ac_submissions[sd['title']]]:
                    continue
            self.ac_submissions[sd['title']].append(sd)

    def prepare_solutions(self):
        solu_file = os.path.join(PREFIX, '_cache', 'solutions.json')
        if os.path.exists(solu_file):
            with open(solu_file, 'r', encoding='utf-8') as f:
                self.solutions = json.load(f)
        print('> Get solutions')
        for title, sublist in self.ac_submissions.items():
            print(title)
            for sub in sublist[::-1]:
                solu = self.user.solution(sub['id'])
                slug = solu['title_slug']
                if slug not in self.solutions:
                    self.solutions[slug] = [solu]
                else:
                    for i in range(len(self.solutions[slug]) - 1, -1, -1):
                        if self.solutions[slug][i]['language'] == solu['language']:
                            self.solutions[slug].pop(i)
                    self.solutions[slug].insert(0, solu)
        with open(solu_file, 'w', encoding='utf-8') as f:
            json.dump(self.solutions, f)

    def prepare_questions(self):
        ques_file = os.path.join(PREFIX, '_cache', 'questions.json')
        if os.path.exists(ques_file):
            with open(ques_file, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
        cn_user = UserCNSP()  # Chinese version comes with translation
        print('> Get questions')
        for slug in self.solutions:
            if slug not in self.questions:
                print(slug)
                self.questions[slug] = cn_user.question(slug)
        with open(ques_file, 'w', encoding='utf-8') as f:
            json.dump(self.questions, f)

    def prepare_notes(self):
        note_file = os.path.join(PREFIX, '_cache', 'notes.json')
        if os.path.exists(note_file):
            with open(note_file, 'r', encoding='utf-8') as f:
                self.notes = json.load(f)
        print('> Get notes')
        for slug in self.solutions:
            if slug not in self.notes:
                print(slug)
                self.notes[slug] = self.user.note(self.questions[slug]['questionId'])
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(self.notes, f)

    def prepare_likes(self):
        like_file = os.path.join(PREFIX, '_cache', 'likes.json')
        if os.path.exists(like_file):
            with open(like_file, 'r', encoding='utf-8') as f:
                self.likes = json.load(f)
        print('> Get likes')
        for slug in self.solutions:
            if slug not in self.likes:
                print(slug)
                self.likes[slug] = self.user.likes(slug)
        with open(like_file, 'w', encoding='utf-8') as f:
            json.dump(self.likes, f)

    @staticmethod
    def prepare_render():
        # delete folder "repo"
        shutil.rmtree(os.path.join(PREFIX, 'repo'), ignore_errors=True)
        os.makedirs(os.path.join(PREFIX, 'repo'))
        os.makedirs(os.path.join(PREFIX, 'repo', 'problems'))

    def render_readme(self):
        print('> Render README.md')
        # This determines how to sort the problems
        ques_sort = sorted(
            [(ques['questionFrontendId'], ques['questionTitleSlug']) for ques in self.questions.values()],
            key=lambda x: -1 * int(x[0]))
        # You can customize the template
        tmpl = Template(open(os.path.join(PREFIX, 'templ', 'README.md.txt'), encoding='utf-8').read())
        readme = tmpl.render(questions=[self.questions[slug] for _, slug in ques_sort], likes=self.likes)
        with open(os.path.join(PREFIX, 'repo', 'README.md'), 'w', encoding='utf-8') as f:
            f.write(readme)

    def render_problems(self):
        print('> Render problems')
        # You can customize the template
        tmpl = Template(
            open(os.path.join(PREFIX, 'templ', 'question.md.txt'), encoding='utf-8').read())
        for slug in self.solutions:
            _question = self.questions[slug]
            _note = self.notes[slug]
            _solutions = self.solutions[slug]
            question = tmpl.render(question=_question, note=_note, solutions=_solutions)
            _filename = '%s-%s.md' % (_question['questionFrontendId'], slug)
            print(_filename)
            with open(os.path.join(PREFIX, 'repo', 'problems', _filename), 'w', encoding='utf-8') as f:
                f.write(question)

    @staticmethod
    def copy_source():
        print('> Copy resources')
        repo = os.path.join(PREFIX, 'repo')
        for src in glob.glob(os.path.join(PREFIX, '_source', '*')):
            print(os.path.relpath(src, PREFIX))
            dst = os.path.join(repo, os.path.basename(src))
            if os.path.isdir(src):
                if not os.path.isdir(dst):
                    shutil.copytree(src, dst)
                else:
                    print("Directory '%s' already exist." % os.path.relpath(dst, PREFIX))
            else:
                shutil.copy(src, repo)

    def deploy(self):
        if self.conf.get('repo'):
            print('> Deploy to git repository')
            repo = os.path.join(PREFIX, 'repo')
            cmds = []
            os.chdir(repo)
            shutil.rmtree(os.path.join(repo, '.git'), ignore_errors=True)
            cmds.append('git init')
            cmds.append('git add .')
            cmds.append('git commit -m "Auto Deployment"')
            for remote in self.conf['repo']:
                cmds.append('git push -f -q %s master:master' % remote)

            for cmd in cmds:
                try:
                    ret = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8').strip()
                    if ret:
                        print(ret)
                except subprocess.CalledProcessError:
                    break


def _main():
    with open(os.path.join(PREFIX, 'config.yml'), encoding='utf-8') as f:
        conf = yaml.load(f)
    rg = RepoGen(conf)
    rg.main()


if __name__ == '__main__':
    _main()
