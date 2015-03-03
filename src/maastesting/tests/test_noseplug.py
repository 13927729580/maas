# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `maastesting.noseplug`."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from optparse import OptionParser
from os import makedirs
from os.path import (
    dirname,
    join,
    )

from maastesting import noseplug
from maastesting.factory import factory
from maastesting.matchers import MockCalledOnceWith
from maastesting.noseplug import Select
from maastesting.testcase import MAASTestCase
from mock import (
    ANY,
    sentinel,
    )
from testtools.matchers import (
    Equals,
    IsInstance,
    MatchesListwise,
    MatchesStructure,
    )
from twisted.python.filepath import FilePath


class TestSelect(MAASTestCase):

    def test__create_has_dirs(self):
        select = Select()
        self.assertThat(
            select, MatchesStructure.byEquality(dirs=frozenset()))

    def test__options_adds_options(self):
        select = Select()
        parser = OptionParser()
        select.options(parser=parser, env={})
        self.assertThat(
            parser.option_list[-2:],
            MatchesListwise([
                # The --with-select option.
                MatchesStructure.byEquality(
                    action="store_true", default=None,
                    dest="enable_plugin_select",
                ),
                # The --select-dir/--select-directory option.
                MatchesStructure.byEquality(
                    action="append", default=[], dest="select_dirs",
                    metavar="DIR", type="string", _short_opts=[],
                    _long_opts=["--select-dir", "--select-directory"],
                )
            ]))

    def test__configure_scans_directories(self):
        directory = self.make_dir()
        segments = factory.make_name("child"), factory.make_name("grandchild")
        makedirs(join(directory, *segments))

        select = Select()
        parser = OptionParser()
        select.add_options(parser=parser, env={})
        options, rest = parser.parse_args(
            ["--with-select", "--select-dir", directory])
        select.configure(options, sentinel.conf)

        leaf = FilePath(directory).descendant(segments)
        expected_dirs = {leaf}
        expected_dirs.update(leaf.parents())
        self.assertThat(select.dirs, Equals(
            set(fp.path for fp in expected_dirs)))

    def test__wantDirectory_checks_dirs_and_thats_it(self):
        directory = self.make_dir()
        segments = factory.make_name("child"), factory.make_name("grandchild")
        makedirs(join(directory, *segments))

        select = Select()
        self.assertFalse(select.wantDirectory(directory))
        select.addDirectory(directory)
        self.assertTrue(select.wantDirectory(directory))
        self.assertTrue(select.wantDirectory(join(directory, *segments)))
        self.assertTrue(select.wantDirectory(dirname(directory)))
        self.assertFalse(select.wantDirectory(
            join(directory, factory.make_name("other-child"))))


class TestMain(MAASTestCase):

    def test__sets_addplugins(self):
        self.patch_autospec(noseplug, "TestProgram")
        noseplug.main()
        self.assertThat(
            noseplug.TestProgram,
            MockCalledOnceWith(addplugins=[ANY]))
        [plugin] = noseplug.TestProgram.call_args[1]["addplugins"]
        self.assertThat(plugin, IsInstance(Select))