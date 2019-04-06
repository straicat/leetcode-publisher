简体中文 | [Enlish](README.EN.md)

## leetcode-publisher

LeetCode 题解仓库自动生成与发布。

样例：[My accepted leetcode solutions](https://github.com/jlice/leetcode)

<p align="center"><img src="https://user-images.githubusercontent.com/9983385/55671789-3bb50a00-58c6-11e9-9296-38c2e98df4cc.gif"></p>

### 使用方法

1. 下载本工具

```Bash
$ git clone https://github.com/jlice/leetcode-publisher.git
```

2. 安装依赖（需要Python 3.5或更高版本）

```Bash
$ cd leetcode-publisher
$ pip install -r requirements.txt
```

3. 配置（复制`config.example.yml`为`config.yml`，然后编辑之）

```Bash
$ cp config.example.yml config.yml
$ vim config.yml
```

4. 尽情使用！

```Bash
$ python src/app.py
```

### 说明

本工具会自动获取你在 LeetCode 上的数据，并缓存至`_cache`文件夹，这样你就不需要从 LeetCode 重复获取数据。

题解仓库生成在`repo`文件夹，每次生成前会删除该文件夹。`_source`文件夹里的内容在生成时会复制到`repo`文件夹下。

README和题解的模板采用[Jinja2](http://jinja.pocoo.org/)编写，位于`templ`文件夹。

只获取与展示通过的代码。如果同一编程语言的代码多次通过，只展示最新的。如果使用多个编程语言答题，会展示多个编程语言的解答。

### 协议

[The MIT License](LICENSE)
