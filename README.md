
爬取单词数据
=======
![](https://img.shields.io/badge/Powered%20by-@Lx.Dong-green.svg)
![](https://img.shields.io/badge/language-Python-green.svg)


* 支持版本: ![](https://img.shields.io/badge/Python-3.x-blue.svg)
           ![](https://img.shields.io/badge/centos-7.x-blue.svg)


### 准备工作

* 下载源码:

      git@github.com:lxdaixin128/words_reptile.git
      或者直接到https://github.com/lxdaixin128/words_reptile.git 下载zip文件

* [安装SSDB](http://ssdb.io/zh_cn/)

* 恢复数据库单词队列（单词总量135120）

      # 将words.ssdb备份文件放入ssdb根目录下
      # 进入ssdb控制台
      # import words.ssdb

  

* [安装爬虫代理池](https://github.com/frankroad/proxy_pool)
  
* 安装依赖:

      pip3 install pyssdb



### 使用

* 后台运行

      nohup python3 -u reptile.py > log 2>&1 & 命令后台运行
      cat log 查看日志
      
* [screen命令](https://blog.csdn.net/zy_zhengyang/article/details/52385887)

      yum install screen
      screen python3 reptile.py

* SSDB可视化工具

     可通过[SSDB可视化工具](https://github.com/jhao104/SSDBAdmin)，访问http://127.0.0.1:5010 查看抓取到的单词。


    
    





