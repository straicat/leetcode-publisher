import json
import re
from functools import partial

import requests
from requests.adapters import HTTPAdapter

DOMAIN_EN = 'https://leetcode.com'
DOMAIN_CN = 'https://leetcode-cn.com'


# noinspection PyPep8Naming
class GraphqlAPI:
    @staticmethod
    def getQuestionDetail(title_slug):
        return '{"operationName":"getQuestionDetail","variables":{"titleSlug":"%s"},"query":"query getQuestionDetail($titleSlug: String!) {\\n  isCurrentUserAuthenticated\\n  question(titleSlug: $titleSlug) {\\n    questionId\\n    questionFrontendId\\n    questionTitle\\n    translatedTitle\\n    questionTitleSlug\\n    content\\n    translatedContent\\n    difficulty\\n    stats\\n    allowDiscuss\\n    contributors {\\n      username\\n      profileUrl\\n      __typename\\n    }\\n    similarQuestions\\n    mysqlSchemas\\n    randomQuestionUrl\\n    sessionId\\n    categoryTitle\\n    submitUrl\\n    interpretUrl\\n    codeDefinition\\n    sampleTestCase\\n    enableTestMode\\n    metaData\\n    langToValidPlayground\\n    enableRunCode\\n    enableSubmit\\n    judgerAvailable\\n    infoVerified\\n    envInfo\\n    urlManager\\n    article\\n    questionDetailUrl\\n    libraryUrl\\n    companyTags {\\n      name\\n      slug\\n      translatedName\\n      __typename\\n    }\\n    companyTagStats\\n    topicTags {\\n      name\\n      slug\\n      translatedName\\n      __typename\\n    }\\n    __typename\\n  }\\n  interviewed {\\n    interviewedUrl\\n    companies {\\n      id\\n      name\\n      slug\\n      __typename\\n    }\\n    timeOptions {\\n      id\\n      name\\n      __typename\\n    }\\n    stageOptions {\\n      id\\n      name\\n      __typename\\n    }\\n    __typename\\n  }\\n  subscribeUrl\\n  isPremium\\n  loginUrl\\n}\\n"}' % title_slug

    @staticmethod
    def getLikesAndFavorites(title_slug):
        return '{"operationName":"getLikesAndFavorites","variables":{"titleSlug":"%s"},"query":"query getLikesAndFavorites($titleSlug: String!) {\\n  question(titleSlug: $titleSlug) {\\n    questionId\\n    likes\\n    dislikes\\n    isLiked\\n    __typename\\n  }\\n  favoritesLists {\\n    publicFavorites {\\n      ...favoriteFields\\n      __typename\\n    }\\n    privateFavorites {\\n      ...favoriteFields\\n      __typename\\n    }\\n    __typename\\n  }\\n}\\n\\nfragment favoriteFields on FavoriteNode {\\n  idHash\\n  id\\n  name\\n  isPublicFavorite\\n  viewCount\\n  creator\\n  isWatched\\n  questions {\\n    questionId\\n    title\\n    titleSlug\\n    __typename\\n  }\\n  __typename\\n}\\n"}' % title_slug

    @staticmethod
    def fetchAllLeetcodeTemplates():
        return '{"operationName":"fetchAllLeetcodeTemplates","variables":{},"query":"query fetchAllLeetcodeTemplates {\\n  allLeetcodePlaygroundTemplates {\\n    templateId\\n    name\\n    nameSlug\\n    __typename\\n  }\\n}\\n"}'


class User:
    def __init__(self, domain):
        self.__domain = domain
        self.sess = requests.Session()
        adapter = HTTPAdapter(max_retries=5)
        self.sess.mount('https://', adapter)
        self.sess.mount('http://', adapter)
        self.sess.request = partial(self.sess.request, timeout=(3.05, 27))

    @property
    def domain(self):
        return self.__domain

    @property
    def csrftoken(self):
        if 'csrftoken' not in self.sess.cookies:
            self.sess.get(self.domain + '/')
        return self.sess.cookies.get('csrftoken')

    def request(self, method, url, **kwargs):
        if not url.startswith('http'):
            url = self.domain + url
        if 'headers' in kwargs:
            head = kwargs['headers']
            del kwargs['headers']
        else:
            head = {'referer': url, 'x-csrftoken': self.csrftoken}
        return self.sess.request(method, url, headers=head, **kwargs)

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
        params = {'offset': (page - 1) * 20, 'limit': 20}
        return self.request('GET', url, params=params).json()

    def solution(self, submission_id):
        url = self.domain + '/submissions/detail/%d/' % submission_id
        html = self.request('GET', url).text
        runtime = re.findall(r"runtime: '(\d+ ms)',", html)[0]
        language = re.findall(r"getLangDisplay: '(\S+?)',", html)[0]
        code = re.findall(r"submissionCode: '(.+?)',\n", html)[0].encode('utf-8').decode('unicode-escape')
        title_slug = re.findall(r"editCodeUrl: '/problems/(\S+?)/'", html)[0]
        return {'runtime': runtime, 'language': language, 'code': code, 'submission_id': submission_id,
                'title_slug': title_slug}

    def note(self, question_id):
        url = self.domain + '/problems/note/%s/' % question_id
        return self.request('GET', url).json().get('content')


class UserEN(User):
    def __init__(self):
        super().__init__(domain=DOMAIN_EN)


class UserCN(User):
    def __init__(self):
        super().__init__(domain=DOMAIN_CN)
