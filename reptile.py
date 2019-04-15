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
import urllib3
local = '127.0.0.1'
ip = local
db = Client(host=ip, port=8888)
threadLock = threading.Lock()
total = db.qsize('words')

cur_speed_level = 1.3

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
    local_catch_count = 0
    c_timeout_count = 0
    r_timeout_count = 0
    del_proxy_count = 0

    def __init__(self):
        self.proxy_list = self.get_proxy_list()

    def get_proxy(self):
        return requests.get("http://{}:5010/get/".format(ip)).text

    def delete_proxy(self, proxy):
        self.del_proxy_count += 1
        requests.get("http://{}:5010/delete/?proxy={}".format(ip, proxy))

    # your spider code
    def get_proxy_list(self):
        rec = json.loads(requests.get("http://{}:5010/get_all/".format(ip)).text)
        return rec

    def getHtml(self, url):
        self.proxy_list = self.get_proxy_list()
        c_timeout = 6
        r_timeout = 9
        if len(self.get_proxy_list()) == 0:
            # 代理池为空时使用本地连接抓取
            if self.local_catch_count > 60:
                time.sleep(10)
                self.local_catch_count -= 2
            self.local_catch_count += 1
            html = requests.get(url)
            text = html.text if html else None
            return text
        else:
            # 使用代理抓取
            retry_count = 2
            proxy = self.get_proxy()
            while retry_count > 0:
                try:
                    html = requests.get(url, proxies={"http": "http://{}".format(proxy)},
                                        timeout=(c_timeout, r_timeout))
                    text = html.text if html else None
                    return text
                except requests.exceptions.ConnectTimeout as e:
                    # print('\n' + '连接超时', e)
                    c_timeout += 1.5
                    if c_timeout > 11:
                        self.c_timeout_count += 1
                        break
                except requests.exceptions.ReadTimeout as e:
                    # print('\n' + '读取超时', e)
                    r_timeout += 1.5
                    if r_timeout > 12:
                        self.r_timeout_count += 1
                        break
                except requests.exceptions.TooManyRedirects as e:
                    # print('\n' + 'urllib3.exceptions.ReadTimeoutError', e)
                    # print('requests.exceptions.TooManyRedirects')
                    return None
                except urllib3.exceptions.ReadTimeoutError as e:
                    # print('\n' + 'urllib3.exceptions.ReadTimeoutError', e)
                    return None
                except requests.exceptions.ProxyError as e:
                    # print('\n' + '代理错误', e)
                    retry_count -= 1
                except requests.exceptions.ConnectionError as e:
                    # print('\n' + 'requests.exceptions.ConnectionError', e)
                    return None

            # 出错2次, 删除代理池中代理
            self.delete_proxy(proxy)
            return None


class EtymaList(object):
    # 代理池对象
    proxy = None
    # 代理池代理数
    proxy_pool = 0

    old_threads = []
    threads = []
    cur_words = []

    # 已完成单词
    cp_count = 0
    # 已扫描单词
    sc_count = 0

    ave_speed = 0
    cur_speed = 0
    slow_speed_count = 0

    def get_next_word_from_que(self, que):
        threadLock.acquire()
        '''获得下个要抓取的单词'''
        word = db.qpop(que).decode()
        db.qpush_back(que, word)
        # 判断该词是否已经抓取
        while self._word_is_avail(word) and self.sc_count < total:
            try:
                if self.sc_count > 10:
                    proportion = self.sc_count / total
                    percent = '%.2f%%' % (proportion * 100)
                    status = '正在搜索单词...' + percent
                    self.show_progress_bar(status)
                self.sc_count += 1
                word = db.qpop(que).decode()
                db.qpush_back(que, word)
            except ConnectionResetError as e:
                print(e)
        if self.sc_count >= total:
            word = None
        if word:
            self.cur_words.append(word)
        threadLock.release()
        return word

    def _word_is_avail(self, word):
        return db.hget('words', word) or db.hget('omit', word) or (word in self.cur_words)
    
    def _get_cur_amount(self):
        self.cur_amount = db.hsize('words') + db.hsize('omit')
        
    def _get_len_proxy_pool(self):
        self.len_proxy_pool = len(self.proxy.proxy_list)

    def _get_len_threads(self):
        return len(self.threads) + len(self.old_threads)

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
        # 重试抓取2次，使用不同代理
        count = 3
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
                    self.process_word_group_html(youdao_html)

        # 获取当前数据库和代理池大小
        self._get_cur_amount()
        self._get_len_proxy_pool()

        if not word_item:
            # 抓取不成功的情况
            self._show_res_info('Failed!', word)
            db.hset('omit', word, 0)
        else:
            # 抓取成功的情况
            self.cp_count += 1

            # 计算平均速度
            self.ave_speed = float('%.2f' % (self.cp_count / (time.time() - self.begin_time)))

            # 计算当前速度
            self.his_time[self.cp_count % 10] = time.time()
            if self.cp_count >= 10:
                self.cur_speed = float('%.2f' % (10 / (time.time() - self.his_time[(self.cp_count % 10 + 1) % 10])))
            else:
                self.cur_speed = float('%.2f' % (self.cp_count / (time.time() - self.his_time[0])))
            
            # 设置慢速标志
            if self.cur_speed < cur_speed_level:
                self.slow_speed_count += 1
            else:
                self.slow_speed_count = 0
                
            # 重置超时标志位
            self.restart_tag = time.time()

            # 更新数据库
            rec = db.hset('words', word, json.dumps(word_item))

            # 打印抓取成功信息
            if rec:
                self._show_res_info('Success!!', word)
        self.cur_words.remove(word)
        self.show_progress_bar('抓取中...')

    def _show_res_info(self, status, word):
        threadLock.acquire()
        # 获取必要数据
        cur_speed = self.cur_speed
        proxy_pool = self.len_proxy_pool
        time_now = datetime.datetime.now().strftime('%m--%d %H:%M:%S')

        # 构建frame
        width = 120
        edge = '~' * (width + 2) + '\n'
        spell = '|' + ' ' * width + '|' + '\n'
        text = '{} , Word: {} , Time: {} , Cur-speed: {}/s , Proxy_pool: {}'.format(
            status, word, time_now, cur_speed, proxy_pool)
        len1 = (width - len(text)) // 2
        len2 = width - len(text) - len1
        main_text = '|' + ' ' * len1 + text + ' ' * len2 + '|' + '\n'
        frame = edge + spell * 3 + main_text + spell * 3 + edge

        print('\r' + frame)
        threadLock.release()

    def catch_words_from_que(self, que):

        def clear_dead_thread(ex):
            '''清理死尸'''
            for th in ex.threads:
                if not th.is_alive():
                    ex.threads.remove(th)
            for th in ex.old_threads:
                if not th.is_alive():
                    ex.old_threads.remove(th)

        while True:
            # 速度过慢标志(连续12次瞬时速度小于1)
            slow_speed_tag = self.slow_speed_count >= 12
            if slow_speed_tag:
                self.slow_speed_count = 0
                self.old_threads.extend(self.threads)
                self.threads.clear()
                print('\n', restart)

            if self.len_proxy_pool == 0:
                self.show_progress_bar('代理池为空，等待60秒...')
                time.sleep(60)
            if len(self.old_threads) > 100:
                self.old_threads.clear()
                self.show_progress_bar('线程过多，休息120秒...')
                time.sleep(120)

            clear_dead_thread(self)

            # 发射抓取线程
            while len(self.threads) < 30:
                word = self.get_next_word_from_que(que)
                while word is None:
                    clear_dead_thread(self)
                    self.show_progress_bar('等待最后结束...')
                    if not self._get_len_threads():
                        self.show_progress_bar('抓取完毕！！')
                        return
                t = threading.Thread(target=self.get_word_info, args=(word,))
                t.setDaemon(True)
                t.start()
                self.threads.append(t)

    def show_progress_bar(self, status):
        # 获取必要数据
        len_threads = self._get_len_threads()
        ave_speed = self.ave_speed
        cur_amount = self.cur_amount
        proportion = cur_amount / total
        percent = '%.2f%%' % (proportion * 100)
        c_timeout_count = self.proxy.c_timeout_count
        r_timeout_count = self.proxy.r_timeout_count
        del_proxy_count = self.proxy.del_proxy_count

        # 构建progress_bar
        bar_info = status + '   ' + '当前进度：{} , 数量：{}  , 平均速度: {}/s , 线程数：{} , 连接/读取超时：{}/{} , 删除代理数：{}' \
            .format(percent, cur_amount, ave_speed, len_threads, c_timeout_count, r_timeout_count, del_proxy_count)
        print('\r' + bar_info + ' ' * 15, end='')


def main():
    test = EtymaList()
<<<<<<< HEAD
    test.catch_words_from_que('words')
    # db.hclear('omit')
    # test.catch_words_from_que('words')



=======
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

        if test.len_proxy_pool == 0:
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
                t = threading.Thread(target=test.get_word_info, args=(word,))
                t.setDaemon(True)
                t.start()
                test.threads.append(t)
>>>>>>> a382a5578bba071e15643cd656c9f38ec2be7a0e


if __name__ == "__main__":
    main()
