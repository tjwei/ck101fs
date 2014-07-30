# encoding: utf8

from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv, exit
import os
from time import time

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context


import gevent
from gevent import monkey
CHUNK_SIZE = 3
monkey.patch_all()

import requests
from cachecontrol import CacheControl
sess = requests.session()
cached_sess = CacheControl(sess)
from lxml import etree
from more_itertools import chunked
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


def retrieve_thread_list(url):
    """
    The url may contains many thread links. We parse them out.
    """
    resp = requests.get(url, headers=REQUEST_HEADERS)
    # parse html
    html = etree.HTML(resp.content)
    links = [l for l in html.xpath(
        '//a') if 'href' in l.attrib and 'title' in l.attrib]
    for link in links:
        url = link.attrib['href']
        title = link.attrib['title']
        if not url.startswith('http'):
            url = BASE_URL + url
        if not thread_id(url):
            continue
        yield title, url


def read_img(img):
    print "fetching %s" % img
    resp = cached_sess.get(img, headers=REQUEST_HEADERS)
    # ignore small images
    content_type, width, height = get_image_info(resp.content)
    if width < 300 or height < 300:
        print "image is too small"
        return
    return resp.content


def get_imgs(url):
    title, image_urls = parse_url(url)
    rtn = []

    def worker(img):
        if not img.startswith('http'):
            return
        content = read_img(img)
        if content:
            rtn.append((img, content))
    for chunked_image_urls in chunked(image_urls, CHUNK_SIZE):
        jobs = [gevent.spawn(worker, image_url)
                for image_url in chunked_image_urls]
        gevent.joinall(jobs)
    return rtn
thread_list = {}


class CK(LoggingMixIn, Operations):

    def good_path(self, path):
        head, tail = os.path.split(path)
        try:
            num = int(tail)
        except:
            raise FuseOSError(ENOENT)
        return num

    def getattr(self, path, fh=None):
        if path == '/':
            st = dict(st_mode=(S_IFDIR | 0755), st_nlink=2)
        else:
            head, tail = os.path.split(path)
            if head == "/":
                if tail in root_list:
                    st = dict(st_mode=(S_IFDIR | 0755), st_nlink=2)
                else:
                    raise FuseOSError(ENOENT)
            else:
                hh, thread = os.path.split(head)
                if thread not in root_list:
                    raise FuseOSError(ENOENT)
                thread_url = root_list[thread]
                if thread_url not in thread_list:
                    raise FuseOSError(ENOENT)
                fn_list = thread_list[thread_url]
                if tail not in fn_list:
                    raise FuseOSError(ENOENT)
                size = fn_list[tail][1]
                st = dict(st_mode=(S_IFREG | 0444), st_size=size)

        st['st_ctime'] = st['st_mtime'] = st['st_atime'] = time()
        return st

    def read(self, path, size, offset, fh):
        head, fn = os.path.split(path)
        hh, thread = os.path.split(head)
        if hh != '/' or thread not in root_list:
            raise FuseOSError(ENOENT)
        thread_url = root_list[thread]
        if thread_url not in thread_list:
            raise FuseOSError(ENOENT)
        fn_list = thread_list[thread_url]
        if fn not in fn_list:
            raise FuseOSError(ENOENT)
        img = fn_list[fn][0]
        rtn = read_img(img)
        return rtn[offset:offset + size]

    def readdir(self, path, fh):
        if path == "/":
            return [".", ".."] + root_list.keys()
        else:
            head, tail = os.path.split(path)
            if head == "/" and tail in root_list:
                url = root_list[tail]
                if url not in thread_list:
                    fn_list = thread_list[url] = {}
                    for img, content in get_imgs(url):
                        fn = img.rsplit("/", 1)[1]
                        fn_list[fn] = (img, len(content))
                return [".", ".."] + thread_list[url].keys()
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
    root_list = dict(retrieve_thread_list(BASE_URL + argv[1]))
    print "starting fuse"
    fuse = FUSE(CK(), argv[2], foreground=True, ro=True)
