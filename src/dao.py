class Dao:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()

    def prepare(self):
        self.cur.execute('''
CREATE TABLE IF NOT EXISTS submission (
    code TEXT,
    compare_result TEXT,
    id INTEGER PRIMARY KEY,
    is_pending TEXT,
    lang TEXT,
    memory TEXT,
    runtime TEXT,
    status_display TEXT,
    timestamp INTEGER,
    title TEXT,
    url TEXT
)''')
        self.cur.execute('''
CREATE TABLE IF NOT EXISTS question (
    content TEXT,
    difficulty TEXT,
    dislikes INTEGER,
    likes INTEGER,
    questionFrontendId TEXT,
    questionId TEXT PRIMARY KEY,
    similarQuestions TEXT,
    `stats` TEXT,
    status TEXT,
    title TEXT,
    titleSlug TEXT,
    topicTags TEXT,
    translatedContent TEXT,
    translatedTitle TEXT
)''')

    def close(self):
        self.cur.close()
        self.conn.close()

    def insert_submissions(self, submissions):
        data = []
        for submission in submissions:
            data.append((
                submission['code'],
                submission['compare_result'],
                submission['id'],
                submission['is_pending'],
                submission['lang'],
                submission['memory'],
                submission['runtime'],
                submission['status_display'],
                submission['timestamp'],
                submission['title'],
                submission['url']
            ))
        self.cur.executemany('''
INSERT INTO submission VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', data)
        self.conn.commit()

    def insert_questions(self, questions):
        data = []
        for question in questions:
            data.append((
                question['content'],
                question['difficulty'],
                question['dislikes'],
                question['likes'],
                question['questionFrontendId'],
                question['questionId'],
                question['similarQuestions'],
                question['stats'],
                question['status'],
                question['title'],
                question['titleSlug'],
                str([tag['name'] for tag in question['topicTags']]),
                question['translatedContent'],
                question['translatedTitle']
            ))
        self.cur.executemany('''
INSERT INTO question VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', data)
        self.conn.commit()

    def get_submissions(self):
        self.cur.execute('''SELECT * FROM submission''')
        return self.cur.fetchall()

    def get_questions(self):
        self.cur.execute('''SELECT * FROM question''')
        return self.cur.fetchall()
