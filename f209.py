from core.Global import *
from core.module import Module
from core.stimer import simpltmr
from core.sender import Sender
import socket
import threading
import struct
import re
import json

SPIN_PERIOD = 0.186 ###@@@!!!@@@### 0.086

CHANCES = 3

def brepr(b):
    if b:
        return ' '.join(['%02X' % i for i in b])
    else:
        return '<nothing>'

EOT = b'\x04'
LF = b'\x0a'
CR = b'\x0d'
DLE = b'\x10'
DC1 = b'\x11'
DC3 = b'\x13'
ESC = b'\x1b'
GS = b'\x1d'
US = b'\x1f'


class F209(Module):
    CMDS = {
            'Printer initialization': ESC + b'@',
            'Full cut': ESC + b'i',
            'Partial cut': ESC + b'm',
            'Character code table selection': ESC + b't',
            'Printer status transmission': ESC + b'v',
            'Print and line feed': LF,
            'Print and N lines feed': ESC + b'd',
            'Carriage return': CR,
            'Software reset': DC1,
            'Line print permission': DC3 + b'+',
            'Line print prohibition': DC3 + b'-',
            'Line buffer A selection': DC3 + b'A',
            'Line buffer B selection': DC3 + b'B',
            'Line buffer clear': DC3 + b'C',
            'Model info': ESC + b's\x02',
            'Firmware version info': ESC + b's\x03',
            'Boot version info': ESC + b's\x04',
            'SW setting info': ESC + b's\x05',
    }

    def __init__(self, port_override=None):
        super().__init__()
        self._protocol = 'serial'
        self._port = port_override
        self._check_connection_period = 1.5

    @staticmethod
    def spl(v, l=32):
        w = v.split()
        ret = list()
        ix = 0
        ret.append('')
        for i in w:
            if len(i) > l:
                if len(ret[ix]) > 0:
                    ix += 1
                    ret.append(i)
                else:
                    ret[ix] = i
                ix += 1
                ret.append('')
            elif len(ret[ix]) == 0 and len(i) <= l:
                ret[ix] += i
            elif len(ret[ix]) > 0 and len(ret[ix]) + 1 + len(i) <= l:
                ret[ix] += (' ' + i)
            else:
                ix += 1
                ret.append(i)
        return ret

    def initialize(self):
        # s.write(b'\x1bi')
        # b''
        # s.write(b'\x1bt\x04')
        # b''
        # s.write(b'\x13+')
        # b''
        # s.write(b'\x13A')
        # b''
        # s.write(b'\x13C')
        # b''
        # s.write(b'\x1bv')
        # b'\x00'
        # s.write(b'\x1bs\x02')
        # b'\xff\x02NP-F209 '
        # s.write(b'\x1bs\x03')
        # b'\xff\x03Ver.1.10'
        # s.write('Локер-коробка, уходи!'.encode('cp1251'))
        # b''
        self.update_status('initializing')
        self._execute(self.CMDS['Printer initialization'])
        while Global.run:
            state = self._execute(self.CMDS['Printer status transmission'],
              wait_for_response=True)
            if state and state == b'\x00':
                break
            sleep(0.25)
        self._execute(self.CMDS['Character code table selection'] + b'\x04')
        self._execute(self.CMDS['Line print permission'])
        self._execute(self.CMDS['Line buffer A selection'])
        self._execute(self.CMDS['Line buffer clear'])
        while Global.run:
            state = self._execute(self.CMDS['Printer status transmission'],
              wait_for_response=True)
            if state and state == b'\x00':
                break
            sleep(0.25)
        self.update_status('idle')

    def find_device(self, port, free_ports=None):
        print('$', self.name, 'find device')
        success = False
        self._conn = Sender(port)
        if self._conn:
            model_info = self.get_model_info()
            if model_info and b'NP-F209' in model_info:
                success = True
        self.close_connection()
        if success:
            # got it!
            self._port = port
            return True
        return False

    def check_connection(self, just_after_reconnection=False):
        if self._port:
            state = self.get_state()
            if state and len(state) == 1:
                self._chance = CHANCES
                if just_after_reconnection:
                    self.initialize()
                return True
            else:
                if self._status not in (None, 'no_connection'):
                    self._chance -= 1
                    if self._chance:
                        return True
        return False

    def run(self):
        while Global.run:
            self.spin_once()
            sleep(SPIN_PERIOD)

    def spin_once(self):
        if self._conn:
            sts = self._status
            if sts not in (None, 'no_connection', 'initializing'):
                paper_is_present = self.is_paper_present()
                if paper_is_present == False:
                    self.update_status('no_paper')
                elif paper_is_present == True:
                    self.update_status('idle') ### FIXME
                elif paper_is_present is None:
                    pass # nothing to do with it
                # check connection right now
                try:
                    if not self._conn.conn:
                        self.close_connection()
                except:
                    self.close_connection()

        # serve requests
        rq = self._request
        sts = self._status
        if rq is not None and sts in ('idle', ):
            # print('got a request:', rq)
            if rq.startswith('print'):
                # print('starts with \'print\'')
                text = rq[len('print'):].strip()
                # print('get ready for printing:', text) #@@@
                self.print_text(text)
            elif rq.startswith('cut'):
                self.cut_paper()
            #---
            if rq is not None:
                log.debug('---- clearing request')
                self._request = None

    #####################################################################

    def _execute(self, command, wait_for_response=False):
        response = b''
        if self._conn and command:
            # print('f209 execute: locked????????????????????')
            with self._conn_lock:
                # print('f209 execute: locked!!!!!!!!!!!!!!')
                if type(command) is not list:
                    if type(command) in (int, float):
                        command = [int(command)]
                    if type(command) is str:
                        command = list(command.encode('cp1251'))
                    else:
                        command = list(command)
                log.debug(paint('-------- executing command %s' %
                  brepr(command), YELLOW))
                if self._conn:
                    if wait_for_response:
                        response = self._conn.send_packet(command,
                          total_timeout=0.7)
                    else:
                        response = self._conn.send_packet(command,
                          read_after_send=False)
                    if response:
                        log.debug('-------- response: %s' % brepr(response))
                    try:
                        # disconnected?
                        if not self._conn.conn:
                            self.close_connection()
                    except:
                        self.close_connection()
        return response

    def print_text(self, text=None):
        if text:
            text_list = self.spl(text)
            for line in text_list:
                self._execute(line)
                self._execute(self.CMDS['Print and line feed'])

    def cut_paper(self):
        self._execute(self.CMDS['Print and N lines feed'] + b'\x04')
        self._execute(self.CMDS['Full cut'])

    def get_model_info(self):
        return self._execute(self.CMDS['Model info'], wait_for_response=True)

    def get_state(self):
        state = self._execute(self.CMDS['Printer status transmission'],
          wait_for_response=True)
        return state

    def is_paper_present(self):
        state = self.get_state()
        if not state:
            return None
        elif (state[0] & (1 << 2)) == 0:
            return True
        return False

    #####################################################################
    # requests

    def request_print(self, text=''):
        rq = 'print ' + ' '.join(text.split())
        if not self.is_paper_present():
            log.warning('cannot print ticket: there is no paper in feeder')
            self.update_status('failed >> no paper')
            return False
        return self.check_request_and_status(rq, 'idle')

    def request_cut_paper(self):
        rq = 'cut paper'
        return self.check_request_and_status(rq, 'idle')

