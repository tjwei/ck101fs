# encoding: utf8

from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv, exit
import os
from time import time, mktime
from datetime import datetime
import dateutil.parser
from dateutil.tz import tzlocal
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

import gevent
from gevent import monkey
from gevent.pool import Pool

monkey.patch_all()

import requests
from cachecontrol import CacheControl
sess = requests.session()
cached_sess = CacheControl(sess)
from lxml import etree
from utils import get_image_info, parse_url
from userexc import URLParseError
import re
BASE_URL = 'http://ck101.com/'
REQUEST_HEADERS = {
    'User-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.57 Safari/537.36'}


def thread_id(url):
    try:
        m = re.match('thread-(\d+)-.*', url.rsplit('/', 1)[1])
    except:
        return
    if not m:
        return
    return m.group(1)


import lxml.html
def retrieve_thread_list(url):
    """
    The url may contains many thread links. We parse them out.
    """
    resp = requests.get(url, headers=REQUEST_HEADERS)
    # parse html
    html = lxml.html.fromstring(resp.content)
    links = [l for l in html.xpath('//a') if 'href' in l.attrib]
    for link in links:
        url = link.attrib['href']
        if not thread_id(url):
            continue
        if 'title' in link.attrib:
            title = link.attrib['title']
        else:
            title = link.text_content()
        if not url.startswith('http'):
            url = BASE_URL + url
        yield title, url


def read_img(img):
    print "fetching %s" % img
    resp = cached_sess.get(img, headers=REQUEST_HEADERS)
    # ignore small images
    content_type, width, height = get_image_info(resp.content)
    if width < 300 or height < 300:
        print "image is too small"
        return
    return resp


def get_imgs(url):
    title, image_urls, date = parse_url(url)
    rtn = []

    def worker((n, img)):
        if not img.startswith('http'):
            return
        resp = read_img(img)
        if resp and resp.content:
            entry = {"order": n, "url":img, "size": len(resp.content), "date": datetime.now(tzlocal())}
            if "last-modified" in resp.headers:
                try:                    
                    entry['date']= dateutil.parser.parse(resp.headers['last-modified'])
                except:
                    pass # never mind            
            rtn.append(entry)    
    Pool(5).map(worker, enumerate(image_urls))
    if not date:
        try:
            date = min(x['date'] for x in rtn if 'date' in x)
        except:
            pass #never mind
    return rtn, date




class CK(LoggingMixIn, Operations):
    def __init__(self, root_list):
        self.root = root_list
        self.thread_list = {}
    def get_thread_info(self, path):
        head, tail = os.path.split(path)
        if head == "/" and tail in self.root:
                return self.root[tail]
        return None
        
    def get_file_info(self, path):        
        head, fn = os.path.split(path)
        thread_info = self.get_thread_info(head)
        if not thread_info:
            raise FuseOSError(ENOENT)
        thread_url = thread_info['url']
        if thread_url not in self.thread_list:
            raise FuseOSError(ENOENT)
        fn_list = self.thread_list[thread_url]
        if fn not in fn_list:
            raise FuseOSError(ENOENT)
        return fn_list[fn]

    def getattr(self, path, fh=None):
        if path == '/':
            st = dict(st_mode=(S_IFDIR | 0755), st_nlink=2)
            st['st_ctime'] = st['st_mtime'] = st['st_atime'] = time()
        else:            
            info = self.get_thread_info(path)
            if info:            
                st = dict(st_mode=(S_IFDIR | 0755), st_nlink=2)                
            else:
                info = self.get_file_info(path)
                size = info["size"]
                st = dict(st_mode=(S_IFREG | 0444), st_size=size)
            if "date" in info:
                # print info['date']
                st['st_ctime'] = st['st_mtime'] = st['st_atime'] = mktime(info['date'].timetuple())
            else:
                st['st_ctime'] = st['st_mtime'] = st['st_atime'] = time()                
        return st    

    def read(self, path, size, offset, fh):
        info = self.get_file_info(path)
        img = info["url"]
        resp = read_img(img)
        return resp.content[offset:offset + size]

    def readdir(self, path, fh):
        if path == "/":
            return [".", ".."] + sorted(self.root.keys(), key=lambda x:self.root[x]['date'])
        else:
            thread_info = self.get_thread_info(path)            
            if thread_info:
                url = thread_info["url"]
                if url not in self.thread_list:
                    fn_list = self.thread_list[url] = {}
                    imgs, date = get_imgs(url)
                    if date:
                        thread_info['date'] = date                        
                    for n, entry in enumerate(imgs):
                        fn = ("%03d-"%entry['order']) + entry['url'].rsplit("/", 1)[1].split("?", 1)[0]
                        fn_list[fn] = entry
                fn_list = self.thread_list[url]
                return [".", ".."] + sorted(fn_list.keys())
            else:
                raise FuseOSError(ENOENT)

    # Disable unused operations:
    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None


if __name__ == '__main__':
    if len(argv) != 3:
        print('usage: %s <ck101 url> <mountpoint>' % argv[0])
        exit(1)
    print "readling list"
    r = requests.get(BASE_URL, headers=REQUEST_HEADERS)
    print "list done"
    tid_dict={}
    root_list = {}
    for name, url in retrieve_thread_list(BASE_URL + argv[1]):
        tid = thread_id(url)
        if tid in tid_dict:
            if len(name) < len(tid_dict[tid]):
                continue
            root_list.pop(tid_dict[tid])
        tid_dict[tid] = name
        root_list[name] =  {"url": url, 'date': datetime.now(tzlocal())}
    print "starting fuse"
    fuse = FUSE(CK(root_list), argv[2], foreground=True, ro=True)
