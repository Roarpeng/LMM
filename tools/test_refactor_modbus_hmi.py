#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static checks for Modbus TCP HMI refactor of LMM.xml."""
from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "LMM.xml"
NS = {"p": "http://www.plcopen.org/xml/tc6_0200"}


def text(xml: str) -> str:
    return xml


class ModbusHmiXmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = XML.read_text(encoding="utf-8")
        cls.root = ET.fromstring(cls.raw)

    def test_xml_is_well_formed(self):
        self.assertIsNotNone(self.root)

    def test_modbus_tcp_slave_channels_are_64_words(self):
        # Channel 02 = PLC input / FC03 command @1000
        self.assertRegex(
            self.raw,
            r'ParameterId="1001"[^>]*type="std: ARRAY\[0\.\.63\] OF WORD"',
        )
        self.assertRegex(
            self.raw,
            r'<Element name="ReadRegOffSet"[^>]*>1000</Element>',
        )
        self.assertRegex(
            self.raw,
            r'<Element name="ReadRegLeg"[^>]*>64</Element>',
        )
        # Channel 01 = PLC output / FC16 status @1100
        self.assertRegex(
            self.raw,
            r'ParameterId="2000"[^>]*type="std: ARRAY\[0\.\.63\] OF WORD"',
        )
        self.assertRegex(
            self.raw,
            r'<Element name="WriteRegOffSet"[^>]*>1100</Element>',
        )
        self.assertRegex(
            self.raw,
            r'<Element name="WriteRegLeg"[^>]*>64</Element>',
        )

    def test_process_image_gvl_exists(self):
        self.assertIn('name="MB_CmdIn"', self.raw)
        self.assertIn('address="%IW103"', self.raw)
        self.assertIn('name="MB_StatusOut"', self.raw)
        self.assertIn('address="%QW44"', self.raw)
        self.assertRegex(
            self.raw,
            r'name="MB_CmdIn"[\s\S]{0,400}?<array>[\s\S]{0,120}?lower="0"[\s\S]{0,40}?upper="63"',
        )
        self.assertRegex(
            self.raw,
            r'name="MB_StatusOut"[\s\S]{0,400}?<array>[\s\S]{0,120}?lower="0"[\s\S]{0,40}?upper="63"',
        )

    def test_prg_tcphmi_no_longer_uses_json_tcp_server(self):
        self.assertNotIn('derived name="FB_TCPServer"', self.raw)
        self.assertNotIn('<pou name="FB_TCPServer"', self.raw)
        self.assertNotIn('pathStructure isFolder="False" name="FB_TCPServer"', self.raw)
        # Must still exist and consume process image
        self.assertIn('<pou name="PRG_TcpHmi"', self.raw)
        self.assertIn("MB_CmdIn", self.raw)
        self.assertIn("MB_StatusOut", self.raw)
        self.assertIn("Tcp_xConnected", self.raw)
        self.assertNotIn('FIND(strLine', self.raw)

    def test_plc_prg_order_unchanged(self):
        m = re.search(
            r'<pou name="PLC_PRG" pouType="program">[\s\S]*?<body>\s*<ST>\s*<xhtml[^>]*>([\s\S]*?)</xhtml>',
            self.raw,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("PRG_TcpHmi();", body)
        self.assertIn("PRG_Logic();", body)
        self.assertLess(body.find("PRG_TcpHmi();"), body.find("PRG_Logic();"))


if __name__ == "__main__":
    unittest.main()
