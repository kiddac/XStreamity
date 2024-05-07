#!/usr/bin/python
# -*- coding: utf-8 -*-

def check_internet():
    try:
        with open('/proc/net/route', 'r') as f:
            for line in f:
                # print("*** line ***", line)
                fields = line.strip().split()
                if len(fields) >= 2:
                    interface, dest = fields[:2]
                    if dest == '00000000':  # Default route
                        return True
    except IOError:
        return True

    return False
