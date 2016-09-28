=====
About
=====

`pyhttp` is HTTP/HTTPS benchmarking tool. It supports proxy tunneling.
It's use is identical to `ab <http://httpd.apache.org/docs/2.2/programs/ab.html>`_.

The motivation behind this tool is that `ab` does not support proxy tunneling
when testing with HTTPS.

Tested only on python 2.7.


Sample use
==========

::

	$ ./pyhttp -c 100 -n 500 -P username:password \
		-X 1.2.3.4:8080 http://target.com
