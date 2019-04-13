# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   File Name:      Reptile
   Description :   爬取有道，金山单词数据
   Author :        Lx.Dong
   Date:           2019/04/13
-------------------------------------------------
   Update:
                   2019/04/13
-------------------------------------------------
"""
__Author__ = 'Lx.Dong'

from pyssdb import Client
import re
import datetime
import json
from lxml import etree
import requests
import threading
import time
local = '127.0.0.1'
ip = local
db = Client(host=ip, port=8888)
threadLock = threading.Lock()
total = db.qsize('words')

restart = '''
++++++++       +++++++++++     +++++++++++         +++          ++++++++        *************  
+       +      +             +                    +   +         +       +             *        
+        +     +            +                    +     +        +        +            *        
+       +      +            +                    +     +        +       +             *        
+++++++        +              +                 +       +       +++++++               *        
+     +        +++++++++++      +++++++        +++++++++++      +     +               *        
+       +      +                        +     +           +     +       +             *        
+        +     +                         +    +           +     +        +            *        
+         +    +                         +   +             +    +         +           *        
+          +   +                        +    +             +    +          +          *        
+           +  +++++++++++   ++++++++++     +               +   +           +         *   
'''

class ProxyPool(object):
    proxy_list = []

    def __init__(self):
        self.proxy_list = self.get_proxy_list()

    def get_proxy(self):
        return requests.get("http://{}:5010/get/".format(ip)).text

    def delete_proxy(self, proxy):
        requests.get("http://{}:5010/delete/?proxy={}".format(ip, proxy))

    # your spider code
    def get_proxy_list(self):
        rec = json.loads(requests.get("http://{}:5010/get_all/".format(ip)).text)
        return rec

    def getHtml(self, url):
        self.proxy_list = self.get_proxy_list()
        if len(self.get_proxy_list()) <= 1:
            # 代理池代理数小于2时使用本地连接抓取
            html = requests.get(url)
            text = html.text if html else None
            return text
        else:
            # 使用代理抓取
            retry_count = 2
            proxy = self.get_proxy()
            while retry_count > 0:
                try:

                    html = requests.get(url, proxies={"http": "http://{}".format(proxy)})
                    text = html.text if html else None
                    return text
                except Exception:
                    retry_count -= 1
            # 出错2次, 删除代理池中代理
            self.delete_proxy(proxy)
            return None


class EtymaList(object):
    proxy = None
    old_threads = []
    threads = []
    count = 0
    ave_speed = 0
    cur_speed = 0
    proxy_pool = 0

    def get_next_word(self):
        threadLock.acquire()
        '''获得下个要抓取的单词'''
        word = db.qpop('words').decode()
        db.qpush_back('words', word)
        threadLock.release()
        # 判断该词是否已经抓取
        if db.hget('words', word) or db.hget('omit', word):
            word = None
        return word
    
    def _get_cur_amount(self):
        self.cur_amount = db.hsize('words') + db.hsize('omit')
        
    def _get_len_proxy_pool(self):
        self.len_proxy_pool = len(self.proxy.proxy_list)

    def __init__(self):
        self.proxy = ProxyPool()
        self.his_time = [time.time()] * 10
        self.begin_time = time.time()
        self.restart_tag = time.time()
        self._get_cur_amount()
        self._get_len_proxy_pool()

    def get_html_from_url(self, url):
        proxy = self.proxy
        rec = None
        html = None
        # 重试抓取1次，使用不同代理
        count = 2
        while count > 0 and not rec:
            rec = proxy.getHtml(url)
            html = etree.HTML(rec) if rec else None
            count -= 1
        return html  # html 可以为空

    def get_word_html_from_youdao(self, word):
        url = 'http://dict.youdao.com/w/eng/' + str(word)
        html = self.get_html_from_url(url)
        return html

    def get_word_html_from_ciba(self, word):
        url = 'http://www.iciba.com/' + str(word)
        html = self.get_html_from_url(url)
        return html

    def process_from_word_html(self, ciba_html):
        word_item = {}
        # 获取单词
        word = ciba_html.xpath('//h1[@class="keyword"]/text()')
        word_item['word'] = word[0].strip().replace("\'", "\\\'")

        # 获取音标和发音
        pronounce = []
        reobj = re.compile(r'(http:.*?\.mp3)')
        items = ciba_html.xpath('//div[@class="base-speak"]/span')
        for item in items:
            html = etree.HTML(etree.tostring(item))
            list = []
            ph = html.xpath('//span/span/text()')
            phonetic = ph[0] if ph else ''
            en0 = ciba_html.xpath('//span/i/@ms-on-mouseover')[0]
            reo = reobj.findall(str(en0))
            voice_url = reobj.findall(str(en0))[0] if reo else reo
            list.append(phonetic)
            list.append(voice_url)
            pronounce.append(list)
        word_item['pronounce'] = pronounce

        # 获取释义
        trans_container = []
        items = ciba_html.xpath('//ul[contains(@class, "base-list")]/li')
        for item in items:
            html = etree.HTML(etree.tostring(item))
            mean = {}
            mean['prop'] = html.xpath('//span[@class="prop"]/text()')[0]
            mean['mean'] = []
            list = html.xpath('//p/span/text()')
            for li in list:
                mean['mean'].append(li.replace('；', ''))
            trans_container.append(mean)
        word_item['means'] = trans_container

        # 获取变形
        transfer = []
        items = ciba_html.xpath('//li[contains(@class, "change")]/p/span')
        for item in items:
            html = etree.HTML(etree.tostring(item))
            trans = []
            trans.append(html.xpath('//span/text()')[0].strip())
            trans.append(html.xpath('//span/a/text()')[0])
            transfer.append(trans)
        word_item['transfer'] = transfer

        return word_item

    def process_word_group_html(self, html):
        items = html.xpath('//div[@id="wordGroup2"]/p')
        for item in items:
            html = etree.HTML(etree.tostring(item))
            en = (html.xpath('//p/span/a/text()'))[0]
            cn = (''.join(html.xpath('//p/text()')).replace(' ', '')
                  .replace('\n', '').replace('\r', '').replace('；', ';'))
            db.hset('phrase', en, cn)

    def get_word_info(self, word):
        word_item = {}
        ciba_html = self.get_word_html_from_ciba(word)
        if ciba_html is not None:
            validity = ciba_html.xpath('//h1[@class="keyword"]/text()')
            if validity:
                word_item = self.process_from_word_html(ciba_html)
                youdao_html = self.get_word_html_from_youdao(word)

                if youdao_html is not None:
                    # 获取词组 仅更新当前级
                    self.process_word_group_html(youdao_html)  # 添加词组到数据库

        # 获取当前数据库和代理池大小
        self._get_cur_amount()
        self._get_len_proxy_pool()

        if not word_item:
            # 抓取不成功的情况
            self._show_res_info('Failed!', word)
            db.hset('omit', word, 0)
        else:
            # 抓取成功的情况

            # 更新数据库
            db.hset('words', word, json.dumps(word_item))

            # 计算平均速度
            self.count += 1
            self.ave_speed = '%.2f' % (self.count / (time.time() - self.begin_time))

            # 计算当前速度
            self.his_time[self.count % 10] = time.time()
            if self.count >= 10:
                self.cur_speed = '%.2f' % (10 / (time.time() - self.his_time[(self.count % 10 + 1) % 10]))
            else:
                self.cur_speed = '%.2f' % (self.count / (time.time() - self.his_time[0]))

            # 超时标志位
            self.restart_tag = time.time()

            # 打印抓取成功信息
            self._show_res_info('Success!!', word)

    def _show_res_info(self, status, word):
        threadLock.acquire()
        # 获取必要数据
        len_threads = len(self.threads) + len(self.old_threads)
        ave_speed = self.ave_speed
        cur_speed = self.cur_speed
        proxy_pool = self.len_proxy_pool
        time_now = datetime.datetime.now().strftime('%m--%d %H:%M:%S')
        cur_amount = self.cur_amount
        proportion = cur_amount / total
        percent = '%.2f%%' % (proportion * 100)

        # 构建frame
        edge = '~' * 162 + '\n'
        spell = '|' + ' ' * 160 + '|' + '\n'
        text = '{} , Word: {} , time: {} , ave-speed: {}/s , cur-speed: {}/s , proxy_pool: {}'.format(
            status, word, time_now, ave_speed, cur_speed, proxy_pool)
        len1 = (160 - len(text)) // 2
        len2 = 160 - len(text) - len1
        main_text = '|' + ' ' * len1 + text + ' ' * len2 + '|' + '\n'
        frame = edge + spell * 3 + main_text + spell * 3 + edge

        # 构建progress_bar
        bar_len = 50
        equate = round(bar_len * proportion)
        space = bar_len - equate - 1
        bar = '[' + '-' * equate + '>' + ' ' * space + ']'
        bar_info = '当前进度：{} , 数量：{} , 线程数：{}          ' \
            .format(percent, cur_amount, len_threads)
        progress_bar = bar_info + '     ' + bar

        print('\r' + frame + '\n' + progress_bar, end='')
        threadLock.release()


def main():
    test = EtymaList()
    while test.cur_amount < total:
        # 超时标志
        time_out_tag = (time.time() - test.restart_tag) > 60
        # 速度过慢标志
        slow_speed_tag = test.count > 20 and float(test.ave_speed) < 1.5
        if slow_speed_tag or time_out_tag:
            test.old_threads = test.threads.copy()
            test.threads.clear()
            test = EtymaList()
            print('\n', restart)

        if test.proxy_pool == 0:
            time.sleep(60)
        for th in test.threads:
            if not th.is_alive():
                test.threads.remove(th)
        for th in test.old_threads:
            if not th.is_alive():
                test.old_threads.remove(th)
        while len(test.threads) < 20:
            word = test.get_next_word()
            if word:
                t = threading.Thread(target=test.get_word_info, args=word)
                t.setDaemon(True)
                t.start()
                test.threads.append(t)


if __name__ == "__main__":
    main()
