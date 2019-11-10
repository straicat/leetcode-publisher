import glob
import itertools
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import yaml
from jinja2 import Template

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from leetcode import UserCN, UserEN

LP_PREFIX = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def console(*args, **kwargs):
    sep = kwargs.get('sep') or ' '
    logging.info(sep.join(map(str, args)))
    args = tuple(str(arg).encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding) for arg in args)
    print(*args, **kwargs)


class RepoGen:

    def __init__(self, conf):
        self.conf = conf
        self.user = None
        self.all_submissions = []
        self.new_ac_submissions = defaultdict(list)
        self.new_ac_title_slugs = set()
        self.solutions = {}
        self.questions = {}
        self.notes = {}
        self.likes = {}
        self.templates = {'solution': ''}

    def main(self):
        self.logger()
        console('{0} leetcode publisher start {0}'.format('=' * 20))
        # noinspection PyBroadException
        try:
            if self.login():
                console('> Login successful!')
                self.prepare_templates()
                self.fetch_notes()
                self.prepare_submissions()
                self.prepare_solutions()
                self.prepare_questions()
                # self.prepare_likes()
                self.prepare_render()
                self.render_readme()
                self.render_problems()
                self.copy_source()
                self.deploy()
            else:
                console('> Login failed!')
        except Exception as e:
            logging.exception(e)
        console('{0} leetcode publisher end {0}'.format('=' * 20))

    @staticmethod
    def logger():
        log_file = os.path.join(LP_PREFIX, '_cache', 'log', '%s.log' % datetime.now().strftime('%Y-%m-%d'))
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
        self.conf['account']['domain'] = self.conf['account'].get('domain', 'en').lower()
        domain = self.conf['account']['domain'].lower()
        if domain == 'cn':
            self.user = UserCN()
        elif domain == 'en':
            self.user = UserEN()
        else:
            raise ValueError("Unrecognized domain: '{}'".format(domain))
        return self.user.login(self.conf['account']['user'], self.conf['account']['password'])
    
    def prepare_templates(self):
        self.get_solution_template()

    def get_solution_template(self):
        solution_txt = os.path.join(LP_PREFIX, 'templ', 'solution.txt')
        if os.path.isfile(solution_txt):
            with open(solution_txt, encoding='utf8') as fp:
                self.templates['solution'] = fp.read()

    def __submissions(self):
        sub_file = os.path.join(LP_PREFIX, '_cache', 'submissions.json')
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
        print('\r', end='', flush=True)
        console('> Get submission record completed!            ')

        with open(sub_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_submissions, f)

    def prepare_submissions(self):
        for sd in self.__submissions():
            if sd['status_display'] != 'Accepted':
                continue
            if sd['title'] in self.new_ac_submissions:
                if sd['lang'] in [sub['lang'] for sub in self.new_ac_submissions[sd['title']]]:
                    continue
            self.new_ac_submissions[sd['title']].append(sd)
    
    def get_pin_solutions(self):
        pin_solutions = dict()
        for slug, note in self.notes.items():
            pin_solutions[slug] = list(map(int, re.findall(r'<!--&(\d+)-->', note)))
        return pin_solutions

    def prepare_solutions(self):
        solu_file = os.path.join(LP_PREFIX, '_cache', 'solutions.json')
        if os.path.exists(solu_file):
            with open(solu_file, 'r', encoding='utf-8') as f:
                self.solutions = json.load(f)
        pin_solutions = self.get_pin_solutions()
        console('> Get solutions')
        for title, sublist in self.new_ac_submissions.items():
            console(title)
            for sub in sublist[::-1]:
                solu = self.user.solution(sub['id'])
                slug = solu['title_slug']
                self.new_ac_title_slugs.add(slug)
                if slug not in self.solutions:
                    self.solutions[slug] = [solu]
                else:
                    for i in range(len(self.solutions[slug]) - 1, -1, -1):
                        if self.solutions[slug][i]['language'] == solu['language']:
                            if solu['submission_id'] not in pin_solutions.get(slug, []):
                                self.solutions[slug].pop(i)
                    self.solutions[slug].insert(0, solu)
        # fetch remain pin solutions
        for slug, solution_ids in pin_solutions.items():
            for solution_id in solution_ids:
                if solution_id not in self.solutions.get(slug, []):
                    solution = self.user.solution(solution_id)
                    self.solutions[slug].append(solution)
        with open(solu_file, 'w', encoding='utf-8') as f:
            json.dump(self.solutions, f)

    def prepare_questions(self):
        ques_file = os.path.join(LP_PREFIX, '_cache', 'questions.json')
        if os.path.exists(ques_file):
            with open(ques_file, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
        cn_user = UserCN()  # Chinese version comes with translation
        en_user = UserEN()
        console('> Fix questionFrontendId')
        for slug, question in self.questions.items():
            try:
                front_id = int(question['questionFrontendId'])
            except ValueError:
                pass
            else:
                if front_id > 5000:
                    console(slug)
                    self.questions[slug]['questionFrontendId'] = en_user.question(slug)['questionFrontendId']

        console('> Get questions')
        for slug in self.solutions:
            if slug not in self.questions:
                console(slug)
                # if there is no the question in LeetCode China, try to search it in LeetCode main site instead
                self.questions[slug] = cn_user.question(slug) or en_user.question(slug)

        with open(ques_file, 'w', encoding='utf-8') as f:
            json.dump(self.questions, f)

    def fetch_notes(self):
        console('> Get notes')
        notes = self.user.notes()
        self.notes = {
            obj['question']['titleSlug']: obj['content'] for obj in notes
        }

    def prepare_notes(self):
        """Deprecated. Because of `fetch_notes`"""
        note_file = os.path.join(LP_PREFIX, '_cache', 'notes.json')
        if os.path.exists(note_file):
            with open(note_file, 'r', encoding='utf-8') as f:
                self.notes = json.load(f)
        console('> Get notes')
        for slug in self.solutions:
            if slug not in self.notes or slug in self.new_ac_title_slugs:
                console(slug)
                self.notes[slug] = self.user.note(self.questions[slug]['questionId'])
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(self.notes, f)

    def prepare_likes(self):
        like_file = os.path.join(LP_PREFIX, '_cache', 'likes.json')
        if os.path.exists(like_file):
            with open(like_file, 'r', encoding='utf-8') as f:
                self.likes = json.load(f)
        console('> Get likes')
        for slug in self.solutions:
            if slug not in self.likes or slug in self.new_ac_title_slugs:
                console(slug)
                self.likes[slug] = self.user.likes(slug)
        with open(like_file, 'w', encoding='utf-8') as f:
            json.dump(self.likes, f)

    @staticmethod
    def prepare_render():
        # delete folder "repo"
        shutil.rmtree(os.path.join(LP_PREFIX, 'repo'), ignore_errors=True)
        os.makedirs(os.path.join(LP_PREFIX, 'repo'))
        os.makedirs(os.path.join(LP_PREFIX, 'repo', 'problems'))

    def render_readme(self):
        summary = self.user.summary()
        console('> Render README.md')
        # This determines how to sort the problems
        ques_sort = sorted(
            [(ques['questionFrontendId'], ques['titleSlug']) for ques in self.questions.values()],
            key=lambda x: -int(x[0]))
        # You can customize the template
        tmpl = Template(open(os.path.join(LP_PREFIX, 'templ', 'README.md.txt'), encoding='utf-8').read())
        readme = tmpl.render(questions=[self.questions[slug] for _, slug in ques_sort], likes=self.likes,
                             date=datetime.now(), summary=summary, conf=self.conf)
        with open(os.path.join(LP_PREFIX, 'repo', 'README.md'), 'w', encoding='utf-8') as f:
            f.write(readme)

    def render_problems(self):
        console('> Render problems')
        # You can customize the template
        tmpl = Template(
            open(os.path.join(LP_PREFIX, 'templ', 'question.md.txt'), encoding='utf-8').read())
        pin_solutions = self.get_pin_solutions()
        # template for single solution
        solution_templ = Template(self.templates['solution'])
        for slug in self.solutions:
            question = self.questions[slug]
            note = self.notes.get(slug, "")
            answer = note.replace('\n', '\n\n')
            solutions = self.solutions[slug]
            pins = pin_solutions.get(slug, [])
            for solution in solutions:
                submission_id = solution['submission_id']
                if submission_id in pins:
                    answer = answer.replace('<!--&%s-->' % submission_id, solution_templ.render(solution=solution))
                else:
                    answer += '\n\n%s\n' % solution_templ.render(solution=solution)
            content = tmpl.render(question=question, note=note, solutions=solutions,
                                  date=datetime.now(), conf=self.conf, answer=answer)
            if sys.platform != 'win32':
                content = content.replace('\r\n', '\n')
            filename = '%s-%s.md' % (question['questionFrontendId'], slug)
            with open(os.path.join(LP_PREFIX, 'repo', 'problems', filename), 'w', encoding='utf-8') as f:
                f.write(content)

    @staticmethod
    def copy_source():
        console('> Copy resources')
        repo = os.path.join(LP_PREFIX, 'repo')
        for src in glob.glob(os.path.join(LP_PREFIX, '_source', '*')):
            console(os.path.relpath(src, LP_PREFIX))
            dst = os.path.join(repo, os.path.basename(src))
            if os.path.isdir(src):
                if not os.path.isdir(dst):
                    shutil.copytree(src, dst)
                else:
                    console("Directory '%s' already exist." % os.path.relpath(dst, LP_PREFIX))
            else:
                shutil.copy(src, repo)

    def deploy(self):
        if self.conf.get('repo'):
            console('> Deploy to git repository')
            repo = os.path.join(LP_PREFIX, 'repo')
            cmds = []
            os.chdir(repo)
            shutil.rmtree(os.path.join(repo, '.git'), ignore_errors=True)
            cmds.append('git init')
            cmds.append('git add .')
            cmds.append('git commit -m "Auto Deployment"')
            for remote in self.conf['repo']:
                cmds.append('git push -f -q %s master:master' % remote)

            for cmd in cmds:
                console(cmd)
                try:
                    subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8').strip()
                except subprocess.CalledProcessError:
                    console("Get error when run '%s'" % cmd)
                    break


def _main():
    conf_file = os.path.join(LP_PREFIX, 'config.yml')
    if os.path.isfile(conf_file):
        for ec in ('utf-8', 'gb18030', 'gb2312', 'gbk'):
            try:
                with open(conf_file, encoding=ec) as fp:
                    try:
                        from yaml import FullLoader
                        conf = yaml.load(fp, Loader=FullLoader)
                    except ImportError:
                        conf = yaml.load(fp)
                break
            except UnicodeDecodeError:
                continue
            except yaml.YAMLError:
                print('File does not conform to the YAML format specification：%s' % conf_file)
        rg = RepoGen(conf)
        rg.main()
    else:
        print('File does not exist: %s' % conf_file)


if __name__ == '__main__':
    _main()
