"""
This is the data access object (DAO) that will be responsible to contain all the data that is required to represent a
template in Cobbler.

A template may be rendered by a template provider implemented in :meth:`~cobbler.templates`.

This item type was created to allow a more flexible sourcing of templates. If a template source is not a file that is
either built-in or in ``/etc/cobbler/templates``, it will be cached in memory. Allowed sources for templates now
include:

* an absolute file path (relative ones are NOT supported).
* an HTTP(S) URL.
* an environment variable.

Multiple templates for the same functionality may be supplied and stored in Cobbler.

A template source is allowed to be temporarily unavailable if there is another alternative available. The unavailable
template will be marked as unavailable. A warning that the template is unavailable will be emitted into the log.

To mark a template as suitable for a certain functionality (e.g. GRUB submenu) it must be marked with a tag. Tags are
a list of unique str objects that contain alphanumeric characters, underscores and hyphens. Whitespace is not allowed
to be part of a tag.
"""

from typing import TYPE_CHECKING

from cobbler.items import BaseItem

if TYPE_CHECKING:
    from cobbler.api import CobblerAPI


class Template(BaseItem):
    """
    DAO for a template in Cobbler.
    """

    TYPE_NAME = "template"
    COLLECTION_TYPE = "template"

    def __init__(self, api: "CobblerAPI"):
        super().__init__(api)
        self._template_type = ""
        self._template_uri = ""
        self._built_in = False

    def make_clone(self):
        pass
