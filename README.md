ck101fs
=======

ck101 filesystem


我愛卡提諾 https://github.com/tzangms/iloveck101 的 fuse 版本
原始碼修改自 https://github.com/tzangms/iloveck101 的檔案，及 fusepy 的範例。

這是我拿來練習 fuse 用的
![Screen Shot](https://raw.github.com/tjwei/ck101fs/master/ScreenShot.png)

需要 fuse (如 Fuse for OSX) 及 python
需要的 python module 如下 
```
fusepy
CacheControl
requests
gevent
more_itertools
```
全都能用 pip 安裝，除了 fusepy 外，CacheControl 是  requests 的 cache， 其他是 iloveck101 需要的 module。

使用範例：
```
python ck101.py / mnt
python ck101.py beauty mnt
python ck101.py odd mnt
```
可用 Ctrl-C 或 umount 來結束。
因為屬於「雲端檔案系統」，上網抓資料需要時間，等待可以看看 Console 的訊息，顯示上網抓資料的進度。
