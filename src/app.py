import glob
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import yaml
from jinja2 import Template

from dao import Dao

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
        self.solutions = defaultdict(list)
        self.questions = {}
        self.notes = {}
        self.likes = {}
        self.templates = {'solution': ''}
        self.summary = None
        self.dao = Dao(sqlite3.connect(os.path.join(LP_PREFIX, '_cache', 'leetcode.db')))
        self.dao.prepare()

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
                deploy_ret = self.deploy()
                self.after_deploy(deploy_ret)
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
        for subm in self.dao.get_submissions():
            self.all_submissions.append({
                'code': subm[0],
                'compare_result': subm[1],
                'id': subm[2],
                'is_pending': subm[3],
                'lang': subm[4],
                'memory': subm[5],
                'runtime': subm[6],
                'status_display': subm[7],
                'timestamp': subm[8],
                'title': subm[9],
                'url': subm[10]
            })
        self.all_submissions.sort(key=lambda sub: sub['timestamp'], reverse=True)
        all_submission_ids = [submission['id'] for submission in self.all_submissions]

        submission_offset = None
        submission_offset_filename = os.path.join(LP_PREFIX, '_cache', 'submission_offset.txt')
        if os.path.isfile(submission_offset_filename):
            with open(submission_offset_filename, 'r', encoding='utf8') as f:
                submission_offset = f.read().strip()
                if submission_offset:
                    submission_offset = int(submission_offset)

        has_next = True
        stop_flag = False
        page = 0

        while has_next and not stop_flag:
            page += 1
            new_submissions = []
            print('\r> Get submission record of page %d      ' % page, end='', flush=True)
            j = self.user.submissions(page)
            has_next = j['has_next']
            for sd in j['submissions_dump']:
                if sd['id'] in all_submission_ids:
                    cache_pos = all_submission_ids.index(sd['id'])
                    if cache_pos >= 0:
                        for idx in range(cache_pos, len(all_submission_ids)):
                            submission = self.all_submissions[idx]
                            if submission_offset and submission['id'] <= submission_offset:
                                break
                            yield submission
                        stop_flag = True
                        break
                if submission_offset and sd['id'] <= submission_offset:
                    stop_flag = True
                    break
                new_submissions.append(sd)
                yield sd
            new_submissions.sort(key=lambda sub: sub['timestamp'], reverse=True)
            self.dao.insert_submissions(new_submissions)

        print('\r', end='', flush=True)
        console('> Get submission record completed!            ')

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
        self.summary = self.summary or self.user.summary()
        title_slug_map = dict()
        for stat in self.summary['stat_status_pairs']:
            title_slug_map[stat['stat']['question__title']] = stat['stat']['question__title_slug']

        solu_file = os.path.join(LP_PREFIX, '_cache', 'solutions.json')
        if os.path.exists(solu_file):
            with open(solu_file, 'r', encoding='utf-8') as f:
                self.solutions = json.load(f)
        pin_solutions = self.get_pin_solutions()

        submissions = defaultdict(list)
        for submission in self.all_submissions:
            if submission['title'] in title_slug_map:
                submissions[title_slug_map[submission['title']]].append(submission)

        console('> Get solutions')

        counter_init, counter = 0, 0
        for title, sublist in self.new_ac_submissions.items():
            for sub in sublist[::-1]:
                solu = None
                timestamp = None
                if title_slug_map.get(title):
                    if title_slug_map[title] in self.solutions:
                        for solution in self.solutions[title_slug_map[title]]:
                            if solution['submission_id'] == sub['id']:
                                solu = solution
                                solu['id'] = solu['submission_id']
                                break

                    if sub['title'] in title_slug_map and title_slug_map[sub['title']] in submissions:
                        for solution in submissions[title_slug_map[title]]:
                            if solution['id'] == sub['id']:
                                timestamp = solution['timestamp']
                                if '.beats' not in self.templates['solution'] and (
                                        "'beats'" not in self.templates['solution']):
                                    solu = solution
                                    solu['submission_id'] = solu['id']
                                    solu['title_slug'] = title_slug_map[title]
                                    solu['language'] = solu['lang']
                                    break
                if solu is None:
                    solu = self.user.solution(sub['id'])
                    solu['id'] = solu['submission_id']
                    solu['lang'] = solu['language']
                    counter += 1
                    solu['timestamp'] = timestamp
                    console(title)

                slug = solu['title_slug']
                self.new_ac_title_slugs.add(slug)
                if slug not in self.solutions:
                    self.solutions[slug] = [solu]
                else:
                    for i in range(len(self.solutions[slug]) - 1, -1, -1):
                        if self.solutions[slug][i]['language'] == solu['language']:
                            if solu['submission_id'] not in pin_solutions.get(slug, []):
                                self.solutions[slug].pop(i)
                    if solu['id'] not in [subm.get('id', subm.get('submission_id')) for subm in self.solutions[slug]]:
                        self.solutions[slug].insert(0, solu)

            if counter - counter_init > 50:
                with open(solu_file, 'w', encoding='utf-8') as f:
                    json.dump(self.solutions, f)
                counter_init = counter

        # fetch remain pin solutions
        for slug, solution_ids in pin_solutions.items():
            for solution_id in solution_ids:
                if solution_id not in self.solutions.get(slug, {}):
                    if solution_id not in [subm.get('id', subm.get('submission_id')) for subm in self.solutions[slug]]:
                        solution = self.user.solution(solution_id)
                        console(solution['title'])
                        self.solutions[slug].append(solution)
        with open(solu_file, 'w', encoding='utf-8') as f:
            json.dump(self.solutions, f)

    def prepare_questions(self):
        for que in self.dao.get_questions():
            self.questions[que[10]] = {
                'content': que[0],
                'difficulty': que[1],
                'dislikes': que[2],
                'likes': que[3],
                'questionFrontendId': que[4],
                'questionId': que[5],
                'similarQuestions': que[6],
                'stats': que[7],
                'status': que[8],
                'title': que[9],
                'titleSlug': que[10],
                'topicTags': eval(que[11]),
                'translatedContent': que[12],
                'translatedTitle': que[13],
            }
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
        question_buffer = []
        for slug in self.solutions:
            if slug not in self.questions:
                console(slug)
                # if there is no the question in LeetCode China, try to search it in LeetCode main site instead
                question_buffer.append(cn_user.question(slug) or en_user.question(slug))
                self.questions[slug] = question_buffer[-1]

                if len(question_buffer) == 100:
                    self.dao.insert_questions(question_buffer)
                    question_buffer = []
        self.dao.insert_questions(question_buffer)

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
        self.summary = self.summary or self.user.summary()
        console('> Render README.md')
        # This determines how to sort the problems
        ques_sort = sorted(
            [(ques['questionFrontendId'], ques['titleSlug']) for ques in self.questions.values()],
            key=lambda x: -int(x[0]))
        # You can customize the template
        tmpl = Template(open(os.path.join(LP_PREFIX, 'templ', 'README.md.txt'), encoding='utf-8').read())
        readme = tmpl.render(questions=[self.questions[slug] for _, slug in ques_sort], likes=self.likes,
                             date=datetime.now(), summary=self.summary, conf=self.conf)
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
                    return False
        return True

    def after_deploy(self, deploy_ret):
        if deploy_ret:
            submission_offset_filename = os.path.join(LP_PREFIX, '_cache', 'submission_offset.txt')
            with open(submission_offset_filename, 'w', encoding='utf8') as f:
                f.write('%s\n' % max([submission['id'] for submission in self.all_submissions]))
        self.dao.close()


def _main():
    conf_file = os.path.join(LP_PREFIX, 'config.yml')
    if os.path.isfile(conf_file):
        for ec in ('utf-8', 'gb18030', 'gb2312', 'gbk'):
            try:
                with open(conf_file, encoding=ec) as fp:
                    try:
                        # noinspection PyUnresolvedReferences
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
