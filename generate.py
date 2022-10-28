#!/usr/bin/env python3

import htmlsvg
import random, socket, subprocess, os, time, json
from datetime import datetime
import argparse

type_efu = 1
type_text = 4


class ECDCServers:
    def __init__(self, filename):
        self.servers = []
        self.add_csv(filename)


    def getstatus(self, idx):
        return self.servers[idx][2]


    def setstatus(self, idx, flag):
        self.servers[idx][2] = self.servers[idx][2] | flag


    def clearstatus(self, idx, flag):
        self.servers[idx][2] = self.servers[idx][2] & ~flag


    def add_csv(self, filename):
        file = open(filename, "r")
        lines = file.readlines()
        for line in lines:
            line = line.replace(" ", "")
            line = line.replace("\n", "")
            if line[0] != "#" and line != "":
                name, type, status, ip, port, angle, xoff, yoff, grafana = line.split(',')
                type = int(type)
                status = int(status)
                port = int(port)
                angle = int(angle)
                xoff = int(xoff)
                yoff = int(yoff)
                server = [name, type, status, ip, port, angle, xoff, yoff, grafana, ""]
                self.servers.append(server)
        file.close()


class Monitor:
    def __init__(self, serverlist, debug, refresh):
        self.s_ping =  0x80
        self.s_offline = 0x40
        self.s_service = 0x08
        self.s_stage3 = 0x04
        self.s_stage2 = 0x02
        self.s_stage1 = 0x01
        self.lab = serverlist
        self.debug = debug
        self.refresh = refresh
        self.starttime = self.gettime()


    def mprint(self, arg):
        self.file.write(arg + '\n')


    def dprint(self, arg):
        if self.debug:
            print(arg)


    def gettime(self):
        now = datetime.now()
        return now.strftime("%d/%m/%Y %H:%M:%S")


    def is_offline(self, status):
        return status & self.s_offline


    def can_ping(self, status):
        return status & self.s_ping


    def has_service(self, status):
        return status & self.s_service


    # def check_ping_parallel(self, idx, ipaddr):
    #     num_threads = 2 * multiprocessing.cpu_count()
    #     p = multiprocessing.dummy.Pool(num_threads)
    #     p.map(ping, ["172.30.242.{}".format(x) for x in range(start,end)])

    # Check that server can be reached (ping)
    def check_ping(self, ipaddr):
        res = subprocess.Popen(["ping", "-c1", "-W1", ipaddr], stdout=subprocess.PIPE).stdout.read()
        if res.find(b"1 packets transmitted, 1 ") != -1:
            return True
        else:
            self.dprint("ping failed for {}".format(ipaddr))
            return False


    def efu_get_version(self, ipaddr, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ipaddr, port))
            s.send(b"VERSION_GET")
            data = s.recv(256)
            s.close()

            #return " ".join(data.split()[1:4])
            test = "<br>".join(data.decode("utf-8").split()[1:4])
            self.dprint(test)
            return test
        except:
            self.dprint("connection reset (by peer?)")
            return "connection reset (by peer?)";


    def check_efu_pipeline(self, ipaddr, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ipaddr, port))
            s.send(b"RUNTIMESTATS")
            data = s.recv(256)
            s.close()

            if (data.find(b"BADCMD") != -1):
                self.dprint(data)
                return 7
            data = int(data.split()[1])
            return data
        except:
            self.dprint("connection reset (by peer?)")
            return 0;


    # Check that service is running (accept tcp connection)
    def check_service(self, idx, type, ipaddr, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if sock.connect_ex((ipaddr, port)) == 0:
            self.lab.setstatus(idx, self.s_service) #
            if type == type_efu:
                status = self.check_efu_pipeline(ipaddr, port)
                if status == 0:
                    self.lab.clearstatus(idx, self.s_stage1 | self.s_stage2 | self.s_stage3)
                else:
                    self.lab.setstatus(idx, status)
                self.lab.servers[idx][9] = self.efu_get_version(ipaddr, port)

            else:
                self.lab.setstatus(idx, self.s_stage1 | self.s_stage2 | self.s_stage3)
        else:
            self.lab.clearstatus(idx, self.s_service)
            self.dprint("no service for {}:{}".format(ipaddr, port))


    def getstatus(self):
        for idx, res  in enumerate(self.lab.servers):
            name, type, status, ip, port, ang, xo, yo, grafana, sw = res
            if not self.is_offline(status):
                if self.check_ping(ip):
                    self.lab.setstatus(idx, self.s_ping)
                    self.check_service(idx, type, ip, port)
                else:
                    self.lab.clearstatus(idx, self.s_ping)


    def printbox(self, x, y, a, color, motext='', width=20):
        res = '<rect width="{}" height="10" '.format(width)
        res = res + 'x="{}" y="{}" transform="rotate({} 400 200)" '.format(x,y,a)
        if motext != '' and color != "#C0C0C0":
          res = res + 'onmousemove="showTooltip(evt, \'{}\');" onmouseout="hideTooltip();" '.format(motext)
        res = res + 'fill="{}"'.format(color)
        res = res + '/>'
        self.mprint(res)


    def stagestatetocolor(self, stage, state):
        if state & stage:
            return 'green'
        else:
            return 'red'


    def statetocolor(self, stage, state):
        if self.is_offline(state):
            return '#C0C0C0'
        if not self.can_ping(state):
            return 'orange'
        if not self.has_service(state):
            return 'blue'
        if stage == 1:
            return self.stagestatetocolor(stage, state)
        elif stage == 2:
            return self.stagestatetocolor(stage, state)
        elif stage == 4:
            return self.stagestatetocolor(stage, state)
        else:
            return 'green'

    # TODO Coordinates are a mess - center is (400, 200)
    def printinst(self, name, mouseovertext, type, state, angle, ofsx, ofsy):
        boxy = 195 + ofsy
        texty = boxy + 8
        textx = 450 + ofsx
        common = '<text  class="names" y="{}" transform="rotate({} 400 200)"'.format(texty, angle)
        if type == type_efu:
            self.printbox(500 + ofsx, boxy, angle, self.statetocolor(1, state), mouseovertext)
            self.printbox(522 + ofsx, boxy, angle, self.statetocolor(2, state), mouseovertext)
            self.printbox(544 + ofsx, boxy, angle, self.statetocolor(4, state), mouseovertext)
            self.mprint('{} font-size="8px" x="450">{}</text>'.format(common, name))
        elif type == type_text:
            self.mprint('{} font-size="16px" x="{}">{}</text>'.format(common, textx, name))
        else:
            self.printbox(500 + ofsx, boxy, angle, self.statetocolor(1, state), mouseovertext, 35)
            self.mprint('{} font-size="8px" x="{}">{}</text>'.format(common, textx, name))
        self.mprint('')


    def makelegend(self):
        common = '<text class="names" x="630" font-size="8px"'
        self.printbox(600, 50, 0, '#c0c0c0')
        self.mprint('{}  y="57"  >Uncommissioned</text>'.format(common))
        self.printbox(600, 65, 0, 'orange')
        self.mprint('{}   y="72" >No NW connectivity</text>'.format(common))
        self.printbox(600, 80, 0, 'blue')
        self.mprint('{}   y="87" >Service not running</text>'.format(common))
        self.printbox(600, 95, 0, 'green')
        self.mprint('{}   y="102" >Service running - data</text>'.format(common))
        self.printbox(600, 110, 0, 'red')
        self.mprint('{}   y="117" >Service running - no data</text>'.format(common))


    def generatesvg(self):
        self.mprint(htmlsvg.header)

        for name, type, status, ip, port, angle, xo, yo, url, sw in self.lab.servers:
            self.dprint("{} {} {} {}".format(name, type, status, ip))
            if (url != "none"):
                self.mprint('<a href="{}" target="_blank">'.format(url))
            mouseovertext = '{}:{}<br>{}'.format(ip, port, sw)
            self.printinst(name, mouseovertext, type, status, angle, xo, yo)
            if (url != "none"):
                self.mprint('</a>')

        self.makelegend()
        self.mprint('<text x="10" y="5" fill="white" font-size="16px">{}</text>'.format(self.gettime()))
        self.mprint('<text x="690" y="395" fill="black" font-size="8px">started {}</text>'.format(self.starttime))

        self.mprint(htmlsvg.footer)


    def one_pass(self):
        self.file = open("tmp.svg", "w")
        self.getstatus()
        self.generatesvg()
        self.file.close()
        os.rename("tmp.svg", "index.html")

    def run(self):
        while (True):
            start = time.time()
            self.one_pass()
            dt = time.time() - start
            if (self.refresh - dt) > 0:
                time.sleep(self.refresh - dt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-f', '--file', type = str, default = 'utgaard.csv')
    parser.add_argument('-r', '--refresh', type = int, default = 5)
    args = parser.parse_args()

    serverlist = ECDCServers(args.file)
    mon = Monitor(serverlist, args.debug, args.refresh)

    print("Dashboard generator is running ...")
    mon.run()

if __name__ == "__main__":
    main()
