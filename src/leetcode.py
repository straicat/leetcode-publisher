import json
import re
import time
from functools import partial

import requests
from requests.adapters import HTTPAdapter


# noinspection PyPep8Naming
class GraphqlAPI:
    @staticmethod
    def getQuestionDetail(titleSlug):
        return '{"operationName":"questionData","variables":{"titleSlug":"%s"},"query":"query questionData($titleSlug: String!) {\\n  question(titleSlug: $titleSlug) {\\n    questionId\\n    questionFrontendId\\n    boundTopicId\\n    title\\n    titleSlug\\n    content\\n    translatedTitle\\n    translatedContent\\n    isPaidOnly\\n    difficulty\\n    likes\\n    dislikes\\n    isLiked\\n    similarQuestions\\n    contributors {\\n      username\\n      profileUrl\\n      avatarUrl\\n      __typename\\n    }\\n    langToValidPlayground\\n    topicTags {\\n      name\\n      slug\\n      translatedName\\n      __typename\\n    }\\n    companyTagStats\\n    codeSnippets {\\n      lang\\n      langSlug\\n      code\\n      __typename\\n    }\\n    stats\\n    hints\\n    solution {\\n      id\\n      canSeeDetail\\n      __typename\\n    }\\n    status\\n    sampleTestCase\\n    metaData\\n    judgerAvailable\\n    judgeType\\n    mysqlSchemas\\n    enableRunCode\\n    enableTestMode\\n    envInfo\\n    libraryUrl\\n    __typename\\n  }\\n}\\n"}' % titleSlug

    @staticmethod
    def getLikesAndFavorites(titleSlug):
        return '{"operationName":"getLikesAndFavorites","variables":{"titleSlug":"%s"},"query":"query getLikesAndFavorites($titleSlug: String!) {\\n  question(titleSlug: $titleSlug) {\\n    questionId\\n    likes\\n    dislikes\\n    isLiked\\n    __typename\\n  }\\n  favoritesLists {\\n    publicFavorites {\\n      ...favoriteFields\\n      __typename\\n    }\\n    privateFavorites {\\n      ...favoriteFields\\n      __typename\\n    }\\n    __typename\\n  }\\n}\\n\\nfragment favoriteFields on FavoriteNode {\\n  idHash\\n  id\\n  name\\n  isPublicFavorite\\n  viewCount\\n  creator\\n  isWatched\\n  questions {\\n    questionId\\n    title\\n    titleSlug\\n    __typename\\n  }\\n  __typename\\n}\\n"}' % titleSlug

    @staticmethod
    def fetchAllLeetcodeTemplates():
        return '{"operationName":"fetchAllLeetcodeTemplates","variables":{},"query":"query fetchAllLeetcodeTemplates {\\n  allLeetcodePlaygroundTemplates {\\n    templateId\\n    name\\n    nameSlug\\n    __typename\\n  }\\n}\\n"}'

    @staticmethod
    def addQuestionToFavorite(favoriteIdHash, questionId):
        return '{"operationName":"addQuestionToFavorite","variables":{"favoriteIdHash":"%s","questionId":"%s"},"query":"mutation addQuestionToFavorite($favoriteIdHash: String!, $questionId: String!) {\\n  addQuestionToFavorite(favoriteIdHash: $favoriteIdHash, questionId: $questionId) {\\n    ok\\n    error\\n    favoriteIdHash\\n    questionId\\n    __typename\\n  }\\n}\\n"}' % (favoriteIdHash, questionId)

    @staticmethod
    def allQuestions():
        return '{"operationName":"allQuestions","variables":{},"query":"query allQuestions {\\n  allQuestions {\\n    ...questionSummaryFields\\n    __typename\\n  }\\n}\\n\\nfragment questionSummaryFields on QuestionNode {\\n  title\\n  titleSlug\\n  translatedTitle\\n  questionId\\n  questionFrontendId\\n  status\\n  difficulty\\n  isPaidOnly\\n  categoryTitle\\n  __typename\\n}\\n"}'


class User:
    DOMAIN_EN = 'https://leetcode.com'
    DOMAIN_CN = 'https://leetcode-cn.com'

    def __init__(self, domain):
        self.__domain = domain
        self.__options = {}
        self.__variables = {'lastkey': '', 'x-newrelic-id': ''}
        self.sess = requests.Session()
        self.sess.mount('https://', HTTPAdapter(max_retries=5))
        self.sess.request = partial(self.sess.request, timeout=(3.05, 27))
        self.set_options()

    def set_options(self, retry_span=3, retry_times=100, long_wait=60, turn_long_wait_cnt=3, mute_print=False):
        self.__options.update({
            'retry_span': retry_span,
            'retry_times': retry_times,
            'long_wait': long_wait,
            'turn_long_wait_cnt': turn_long_wait_cnt,
            'mute_print': mute_print,
        })

    @property
    def domain(self):
        return self.__domain

    @property
    def csrftoken(self):
        if 'csrftoken' not in self.sess.cookies:
            r = self.sess.get(self.domain + '/')
            xpid = re.findall(r'xpid:"(\w+=*)"', r.text)
            if xpid:
                self.__variables['x-newrelic-id'] = xpid[0]
        return self.sess.cookies.get('csrftoken')

    def request(self, method, url, **kwargs):
        if not url.startswith('http'):
            url = self.domain + url
        head = {'referer': url, 'x-csrftoken': self.csrftoken, 'x-newrelic-id': self.__variables['x-newrelic-id']}
        if 'headers' in kwargs:
            head.update(kwargs['headers'])
            del kwargs['headers']
        span_cnt = 0
        for _ in range(self.__options['retry_times']):
            r = self.sess.request(method, url, headers=head, **kwargs)
            if r.ok:
                return r
            else:
                span_cnt += 1
                if span_cnt % self.__options['turn_long_wait_cnt'] == 0:
                    for t in range(self.__options['long_wait'], 0, -1):
                        if not self.__options['mute_print']:
                            print('\rError %d, Wait for %d seconds...    ' % (r.status_code, t), end='', flush=True)
                        time.sleep(1)
                    if not self.__options['mute_print']:
                        print()
                else:
                    time.sleep(self.__options['retry_span'])
        raise requests.HTTPError

    def login(self, user, password):
        data = {'login': user, 'password': password}
        r = self.request('POST', self.domain + '/accounts/login/', data=data)
        return r.ok

    def graphql(self, payload):
        r = self.request('POST', self.domain + '/graphql', json=json.loads(payload))
        return r.json()

    def question(self, title_slug):
        return self.graphql(GraphqlAPI.getQuestionDetail(title_slug))['data']['question']

    def likes(self, title_slug):
        return self.graphql(GraphqlAPI.getLikesAndFavorites(title_slug))['data']['question']

    def submissions(self, page):
        url = self.domain + '/api/submissions/'
        headers = {'referer': self.domain + '/submissions/'}
        params = {'offset': (page - 1) * 20, 'limit': 20, 'lastkey': self.__variables['lastkey']}
        j = self.request('GET', url, params=params, headers=headers).json()
        self.__variables['lastkey'] = j['last_key']
        return j

    def solution(self, submission_id):
        url = self.domain + '/submissions/detail/%d/' % submission_id
        html = self.request('GET', url).text
        runtime = re.findall(r"runtime: '(\d+ ms)',", html)[0]
        language = re.findall(r"getLangDisplay: '(\S+?)',", html)[0]
        code = re.findall(r"submissionCode: '(.+?)',\n", html)[0]
        for ch in set(re.findall(r'\\u\w{4}', code)):
            code = code.replace(ch, ch.encode('utf-8').decode('unicode-escape'))
        title_slug = re.findall(r"editCodeUrl: '\S*?/problems/(\S+?)/'", html)[0]
        return {'runtime': runtime, 'language': language, 'code': code, 'submission_id': submission_id,
                'title_slug': title_slug}

    def note(self, question_id):
        url = self.domain + '/problems/note/%s/' % question_id
        return self.request('GET', url).json().get('content')

    def notes(self):
        url = self.domain + '/notes/'
        html = self.request('GET', url).text
        notes = re.findall(r"^\s*notes: JSON.parse\('(.*)'\)\s*$", html)[0]
        for ch in set(re.findall(r'\\u\w{4}', notes)):
            notes = notes.replace(ch, ch.encode('utf-8').decode('unicode-escape'))
        return json.loads(notes)

    def summary(self):
        url = self.domain + '/api/problems/all/'
        return self.request('GET', url).json()


class UserEN(User):
    def __init__(self):
        super().__init__(domain=User.DOMAIN_EN)


class UserCN(User):
    def __init__(self):
        super().__init__(domain=User.DOMAIN_CN)
