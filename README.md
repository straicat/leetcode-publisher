Enlish | [简体中文](README.CN.md)

## leetcode-publisher

Automatically generate and publish LeetCode solution repository.

Example: [My accepted leetcode solutions](https://github.com/jlice/leetcode)

### Instructions

1. Download this tool

```Bash
$ git clone https://github.com/jlice/leetcode-publisher.git
```

2. Install dependencies (requires Python 3.5 or higher)

```Bash
$ cd leetcode-publisher
$ pip install -r requirements.txt
```

3. Configure (copy `config.example.yml` to `config.yml` and edit it)

```Bash
$ cp config.example.yml config.yml
$ vim config.yml
```

4. Enjoy it!

```Bash
$ python src/app.py
```

### Description

This tool will automatically retrieve your data on LeetCode and cache it in the `_cache` folder so you don't need to retrieve data from LeetCode repeatedly.

The solution repository is generated in the `repo` folder, which is deleted before each build. The contents of the `_source` folder will be copied to the `repo` folder when the repository is generated.

The template for the README and the solution is written using [Jinja2](http://jinja.pocoo.org/).

### Agreement

[The MIT License](LICENSE)
