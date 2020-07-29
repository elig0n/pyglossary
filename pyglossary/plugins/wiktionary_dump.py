# -*- coding: utf-8 -*-

from time import time as now
import re
import html

from formats_common import *

enable = True
format = "WiktionaryDump"
description = "Wiktionary Dump (.xml)"
extensions = (".xml",)
optionsProp = {
	"encoding": EncodingOption(),
}
depends = {
}


ignorePageTitlePattern = "|"


class Reader(object):
	def __init__(self, glos):
		self._glos = glos
		self._buff = b""
		self._filename = ""
		self._file = None
		self._fileSize = 0
		# self._alts = {}
		# { word => alts }
		# where alts is str (one word), or list of strs
		# we can't recognize alternates unless we keep all data in memory
		# or scan the whole file and read all entries twice
		self.compilePatterns()

	def _readUntil(self, sub: bytes) -> bytes:
		for line in self._file:
			if sub in line:
				return line
			self._buff += line

	def _readSiteInfo(self) -> bytes:
		self._buff = self._readUntil(b"<siteinfo>")
		self._buff += self._readUntil(b"</siteinfo>")
		siteinfoBytes = self._buff
		self._buff = b""
		return siteinfoBytes

	def open(self, filename):
		try:
			from lxml import etree
		except ModuleNotFoundError as e:
			e.msg += ", run `sudo pip3 install lxml` to install"
			raise e

		self._filename = filename
		self._file = open(filename, mode="rb")
		self._fileSize = os.path.getsize(filename)
		log.info(f"fileSize = {self._fileSize}")

		siteinfoBytes = self._readSiteInfo()
		siteinfo = siteinfoBytes.decode("utf-8")
		self._glos.setInfo("siteinfo", siteinfo)
		# TODO: parse siteinfoBytes

	def close(self):
		self._filename = ""
		self._file.close()
		# self._alts = {}

	def __len__(self):
		return 0

	def _readPage(self) -> "lxml.etree.Element":
		from lxml import etree as ET
		pageEnd = self._readUntil(b"</page>")
		if pageEnd is None:
			return
		page = ET.fromstring(self._buff + pageEnd)
		self._buff = b""
		return page

	def __iter__(self) -> "Iterator[BaseEntry]":
		from lxml import etree as ET
		if not self._filename:
			log.error(
				"WikipediaDump: trying to iterate over reader"
				" while it's not open"
			)
			raise StopIteration
		while True:
			page = self._readPage()
			if page is None:
				break
			yield self._getEntryFromPage(page)

	def _sub_internal_link(self, m: re.Match) -> str:
		ref = m.group(1)
		return f'<a href="bword://{html.escape(ref)}">{ref}</a>'

	def compilePatterns(self):
		self._re_internal_link = re.compile(
			r"\[\[(.+?)\]\]",
			re.MULTILINE,
		)
		self._re_translationHeader = re.compile(
			r"^[;*]?\s?{{(.+?)}}: (.+)$",
			re.MULTILINE | re.UNICODE,
		)
		# ideally '# ...'  should become <ol>, and '* ...' become <ul>
		# but that's hard, so we just replace both with '⚫︎ ...'
		self._re_listItem = re.compile(
			r"^[#*] ?(.*)",
			re.MULTILINE,
		)
		self._re_h2 = re.compile(
			r"^==([^=]+)==$",
			re.MULTILINE,
		)
		self._re_h3 = re.compile(
			r"^===([^=]+)===$",
			re.MULTILINE,
		)
		self._re_h4 = re.compile(
			r"^====([^=]+)====$",
			re.MULTILINE,
		)
		self._re_h5 = re.compile(
			r"^=====([^=]+)=====$",
			re.MULTILINE,
		)
		self._re_template = re.compile(
			r"^\{\{(...+?\|...+?)\}\}$",
			re.MULTILINE,
		)
		self._re_qualifier = re.compile(
			r"\{\{qualifier\|(.+?)\}\}",
		)
		self._re_lastLineLink = re.compile(
			"\\n(<a href=[^<>]*>.*</a>)\\s*$",
		)
		self._re_remainDoubleCurlyBraces = re.compile(
			r"^\{\{(.+)\}\}$",
			re.MULTILINE,
		)
		self._re_nonTaggedLine = re.compile(
			r"^([^<\s].+[^>\s])$",
			re.MULTILINE,
		)

	def fixText(self, text: str) -> str:
		text = self._re_internal_link.sub(self._sub_internal_link, text)
		text = self._re_translationHeader.sub(
			r"<h3>\1</h3>\n⚫︎ \2<br>",
			text,
		)
		text = self._re_listItem.sub(r"⚫︎ \1<br>", text)
		text = self._re_h2.sub(r"<h2>\1</h2>", text)
		text = self._re_h3.sub(r"<h3>\1</h3>", text)
		text = self._re_h4.sub(r"<h4>\1</h4>", text)
		text = self._re_h5.sub(r"<h5>\1</h5>", text)
		text = self._re_template.sub(r"<i>Template: \1</i>", text)
		text = self._re_qualifier.sub(r"<i>(\1)</i>", text)
		text = self._re_lastLineLink.sub("\n<br><br>\\1", text)
		text = self._re_remainDoubleCurlyBraces.sub(r"<i>\1</i><br>", text)
		text = self._re_nonTaggedLine.sub(r"\1<br>", text)
		return text

	def _getEntryFromPage(self, page: "lxml.etree.Element") -> "BaseEntry":
		titleElem = page.find(".//title")
		if titleElem is None:
			return
		title = titleElem.text
		if not title:
			return
		textElem = page.find(".//text")
		if textElem is None:
			return
		text = textElem.text
		if not text:
			return
		text = self.fixText(text)
		byteProgress = (self._file.tell(), self._fileSize)
		return self._glos.newEntry(title, text, byteProgress=byteProgress)
