"""
Cobbler module that contains the code for a generic Cobbler item.
"""

# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright 2006-2009, Red Hat, Inc and Others
# SPDX-FileCopyrightText: Michael DeHaan <michael.dehaan AT gmail>

import copy
import enum
import fnmatch
import pprint
from typing import Union, TYPE_CHECKING

import yaml

from cobbler import utils, enums
from cobbler.items import InheritableItem
from cobbler.cexceptions import CX
from cobbler.decorator import InheritableProperty, InheritableDictProperty

if TYPE_CHECKING:
    from cobbler.api import CobblerAPI


class Item(InheritableItem):
    """
    An Item is a serializable thing that can appear in a Collection
    """

    # Constants
    TYPE_NAME = "generic"
    COLLECTION_TYPE = "generic"

    def __find_compare(
        self,
        from_search: Union[str, list, dict, bool],
        from_obj: Union[str, list, dict, bool],
    ):
        """
        Only one of the two parameters shall be given in this method. If you give both ``from_obj`` will be preferred.

        :param from_search: Tries to parse this str in the format as a search result string.
        :param from_obj: Tries to parse this str in the format of an obj str.
        :return: True if the comparison succeeded, False otherwise.
        :raises TypeError: In case the type of one of the two variables is wrong or could not be converted
                           intelligently.
        """
        if isinstance(from_obj, str):
            # FIXME: fnmatch is only used for string to string comparisons which should cover most major usage, if
            #        not, this deserves fixing
            from_obj_lower = from_obj.lower()
            from_search_lower = from_search.lower()
            # It's much faster to not use fnmatch if it's not needed
            if (
                "?" not in from_search_lower
                and "*" not in from_search_lower
                and "[" not in from_search_lower
            ):
                match = from_obj_lower == from_search_lower
            else:
                match = fnmatch.fnmatch(from_obj_lower, from_search_lower)
            return match

        if isinstance(from_search, str):
            if isinstance(from_obj, list):
                from_search = self.api.input_string_or_list(from_search)
                for list_element in from_search:
                    if list_element not in from_obj:
                        return False
                return True
            if isinstance(from_obj, dict):
                from_search = self.api.input_string_or_dict(
                    from_search, allow_multiples=True
                )
                for dict_key in list(from_search.keys()):
                    dict_value = from_search[dict_key]
                    if dict_key not in from_obj:
                        return False
                    if not (dict_value == from_obj[dict_key]):
                        return False
                return True
            if isinstance(from_obj, bool):
                inp = from_search.lower() in ["true", "1", "y", "yes"]
                if inp == from_obj:
                    return True
                return False

        raise TypeError(f"find cannot compare type: {type(from_obj)}")

    def __init__(self, api: "CobblerAPI", is_subobject: bool = False):
        """
        Constructor.  Requires a back reference to the CobblerAPI object.

        NOTE: is_subobject is used for objects that allow inheritance in their trees. This inheritance refers to
        conceptual inheritance, not Python inheritance. Objects created with is_subobject need to call their
        setter for parent immediately after creation and pass in a value of an object of the same type. Currently this
        is only supported for profiles. Subobjects blend their data with their parent objects and only require a valid
        parent name and a name for themselves, so other required options can be gathered from items further up the
        Cobbler tree.

                           distro
                               profile
                                    profile  <-- created with is_subobject=True
                                         system   <-- created as normal

        For consistency, there is some code supporting this in all object types, though it is only usable
        (and only should be used) for profiles at this time.  Objects that are children of
        objects of the same type (i.e. subprofiles) need to pass this in as True.  Otherwise, just
        use False for is_subobject and the parent object will (therefore) have a different type.

        :param api: The Cobbler API object which is used for resolving information.
        :param is_subobject: See above extensive description.
        """
        super().__init__(api=api, is_subobject=is_subobject)
        self._kernel_options: Union[dict, str] = {}
        self._kernel_options_post: Union[dict, str] = {}
        self._autoinstall_meta: Union[dict, str] = {}
        self._fetchable_files: Union[dict, str] = {}
        self._boot_files: Union[dict, str] = {}
        self._template_files = {}
        self._last_cached_mtime = 0
        self._cached_dict = ""
        self._mgmt_classes: Union[list, str] = []
        self._mgmt_parameters: Union[dict, str] = {}

    @InheritableDictProperty
    def kernel_options(self) -> dict:
        """
        Kernel options are a space delimited list, like 'a=b c=d e=f g h i=j' or a dict.

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: The parsed kernel options.
        :setter: The new kernel options as a space delimited list. May raise ``ValueError`` in case of parsing problems.
        """
        return self._resolve_dict("kernel_options")

    @kernel_options.setter
    def kernel_options(self, options):
        """
        Setter for ``kernel_options``.

        :param options: The new kernel options as a space delimited list.
        :raises ValueError: In case the values set could not be parsed successfully.
        """
        try:
            self._kernel_options = self.api.input_string_or_dict(
                options, allow_multiples=True
            )
        except TypeError as error:
            raise TypeError("invalid kernel options") from error

    @InheritableDictProperty
    def kernel_options_post(self) -> dict:
        """
        Post kernel options are a space delimited list, like 'a=b c=d e=f g h i=j' or a dict.

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: The dictionary with the parsed values.
        :setter: Accepts str in above mentioned format or directly a dict.
        """
        return self._resolve_dict("kernel_options_post")

    @kernel_options_post.setter
    def kernel_options_post(self, options):
        """
        Setter for ``kernel_options_post``.

        :param options: The new kernel options as a space delimited list.
        :raises ValueError: In case the options could not be split successfully.
        """
        try:
            self._kernel_options_post = self.api.input_string_or_dict(
                options, allow_multiples=True
            )
        except TypeError as error:
            raise TypeError("invalid post kernel options") from error

    @InheritableDictProperty
    def autoinstall_meta(self) -> dict:
        """
        A comma delimited list of key value pairs, like 'a=b,c=d,e=f' or a dict.
        The meta tags are used as input to the templating system to preprocess automatic installation template files.

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: The metadata or an empty dict.
        :setter: Accepts anything which can be split by :meth:`~cobbler.utils.input_converters.input_string_or_dict`.
        """
        return self._resolve_dict("autoinstall_meta")

    @autoinstall_meta.setter
    def autoinstall_meta(self, options: dict):
        """
        Setter for the ``autoinstall_meta`` property.

        :param options: The new options for the automatic installation meta options.
        :raises ValueError: If splitting the value does not succeed.
        """
        value = self.api.input_string_or_dict(options, allow_multiples=True)
        self._autoinstall_meta = value

    @InheritableProperty
    def mgmt_classes(self) -> list:
        """
        Assigns a list of configuration management classes that can be assigned to any object, such as those used by
        Puppet's external_nodes feature.

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: An empty list or the list of mgmt_classes.
        :setter: Will split this according to :meth:`~cobbler.utils.input_string_or_list`.
        """
        return self._resolve("mgmt_classes")

    @mgmt_classes.setter
    def mgmt_classes(self, mgmt_classes: Union[list, str]):
        """
        Setter for the ``mgmt_classes`` property.

        :param mgmt_classes: The new options for the management classes of an item.
        """
        if not isinstance(mgmt_classes, (str, list)):
            raise TypeError("mgmt_classes has to be either str or list")
        self._mgmt_classes = self.api.input_string_or_list(mgmt_classes)

    @InheritableDictProperty
    def mgmt_parameters(self) -> dict:
        """
        Parameters which will be handed to your management application (Must be a valid YAML dictionary)

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: The mgmt_parameters or an empty dict.
        :setter: A YAML string which can be assigned to any object, this is used by Puppet's external_nodes feature.
        """
        return self._resolve_dict("mgmt_parameters")

    @mgmt_parameters.setter
    def mgmt_parameters(self, mgmt_parameters: Union[str, dict]):
        """
        A YAML string which can be assigned to any object, this is used by Puppet's external_nodes feature.

        :param mgmt_parameters: The management parameters for an item.
        :raises TypeError: In case the parsed YAML isn't of type dict afterwards.
        """
        if not isinstance(mgmt_parameters, (str, dict)):
            raise TypeError("mgmt_parameters must be of type str or dict")
        if isinstance(mgmt_parameters, str):
            if mgmt_parameters == enums.VALUE_INHERITED:
                self._mgmt_parameters = enums.VALUE_INHERITED
                return
            if mgmt_parameters == "":
                self._mgmt_parameters = {}
                return
            mgmt_parameters = yaml.safe_load(mgmt_parameters)
            if not isinstance(mgmt_parameters, dict):
                raise TypeError(
                    "Input YAML in Puppet Parameter field must evaluate to a dictionary."
                )
        self._mgmt_parameters = mgmt_parameters

    @property
    def template_files(self) -> dict:
        """
        File mappings for built-in configuration management

        :getter: The dictionary with name-path key-value pairs.
        :setter: A dict. If not a dict must be a str which is split by
                 :meth:`~cobbler.utils.input_converters.input_string_or_dict`. Raises ``TypeError`` otherwise.
        """
        return self._template_files

    @template_files.setter
    def template_files(self, template_files: dict):
        """
        A comma seperated list of source=destination templates that should be generated during a sync.

        :param template_files: The new value for the template files which are used for the item.
        :raises ValueError: In case the conversion from non dict values was not successful.
        """
        try:
            self._template_files = self.api.input_string_or_dict(
                template_files, allow_multiples=False
            )
        except TypeError as error:
            raise TypeError("invalid template files specified") from error

    @property
    def boot_files(self) -> dict:
        """
        Files copied into tftpboot beyond the kernel/initrd

        :getter: The dictionary with name-path key-value pairs.
        :setter: A dict. If not a dict must be a str which is split by
                 :meth:`~cobbler.utils.input_converters.input_string_or_dict`. Raises ``TypeError`` otherwise.
        """
        return self._resolve_dict("boot_files")

    @boot_files.setter
    def boot_files(self, boot_files: dict):
        """
        A comma separated list of req_name=source_file_path that should be fetchable via tftp.

        .. note:: This property can be set to ``<<inherit>>``.

        :param boot_files: The new value for the boot files used by the item.
        """
        try:
            self._boot_files = self.api.input_string_or_dict(
                boot_files, allow_multiples=False
            )
        except TypeError as error:
            raise TypeError("invalid boot files specified") from error

    @InheritableDictProperty
    def fetchable_files(self) -> dict:
        """
        A comma seperated list of ``virt_name=path_to_template`` that should be fetchable via tftp or a webserver

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: The dictionary with name-path key-value pairs.
        :setter: A dict. If not a dict must be a str which is split by
                 :meth:`~cobbler.utils.input_converters.input_string_or_dict`. Raises ``TypeError`` otherwise.
        """
        return self._resolve_dict("fetchable_files")

    @fetchable_files.setter
    def fetchable_files(self, fetchable_files: Union[str, dict]):
        """
        Setter for the fetchable files.

        :param fetchable_files: Files which will be made available to external users.
        """
        try:
            self._fetchable_files = self.api.input_string_or_dict(
                fetchable_files, allow_multiples=False
            )
        except TypeError as error:
            raise TypeError("invalid fetchable files specified") from error

    def sort_key(self, sort_fields: list):
        """
        Convert the item to a dict and sort the data after specific given fields.

        :param sort_fields: The fields to sort the data after.
        :return: The sorted data.
        """
        data = self.to_dict()
        return [data.get(x, "") for x in sort_fields]

    def find_match(self, kwargs, no_errors=False):
        """
        Find from a given dict if the item matches the kv-pairs.

        :param kwargs: The dict to match for in this item.
        :param no_errors: How strict this matching is.
        :return: True if matches or False if the item does not match.
        """
        # used by find() method in collection.py
        data = self.to_dict()
        for (key, value) in list(kwargs.items()):
            # Allow ~ to negate the compare
            if value is not None and value.startswith("~"):
                res = not self.find_match_single_key(data, key, value[1:], no_errors)
            else:
                res = self.find_match_single_key(data, key, value, no_errors)
            if not res:
                return False

        return True

    def find_match_single_key(self, data, key, value, no_errors: bool = False) -> bool:
        """
        Look if the data matches or not. This is an alternative for ``find_match()``.

        :param data: The data to search through.
        :param key: The key to look for int the item.
        :param value: The value for the key.
        :param no_errors: How strict this matching is.
        :return: Whether the data matches or not.
        """
        # special case for systems
        key_found_already = False
        if "interfaces" in data:
            if key in [
                "cnames",
                "connected_mode",
                "if_gateway",
                "ipv6_default_gateway",
                "ipv6_mtu",
                "ipv6_prefix",
                "ipv6_secondaries",
                "ipv6_static_routes",
                "management",
                "mtu",
                "static",
                "mac_address",
                "ip_address",
                "ipv6_address",
                "netmask",
                "virt_bridge",
                "dhcp_tag",
                "dns_name",
                "static_routes",
                "interface_type",
                "interface_master",
                "bonding_opts",
                "bridge_opts",
                "interface",
            ]:
                key_found_already = True
                for (name, interface) in list(data["interfaces"].items()):
                    if value == name:
                        return True
                    if value is not None and key in interface:
                        if self.__find_compare(interface[key], value):
                            return True

        if key not in data:
            if not key_found_already:
                if not no_errors:
                    # FIXME: removed for 2.0 code, shouldn't cause any problems to not have an exception here?
                    # raise CX("searching for field that does not exist: %s" % key)
                    return False
            else:
                if value is not None:  # FIXME: new?
                    return False

        if value is None:
            return True
        return self.__find_compare(value, data[key])

    def dump_vars(
        self, formatted_output: bool = True, remove_dicts: bool = False
    ) -> Union[dict, str]:
        """
        Dump all variables.

        :param formatted_output: Whether to format the output or not.
        :param remove_dicts: If True the dictionaries will be put into str form.
        :return: The raw or formatted data.
        """
        raw = utils.blender(self.api, remove_dicts, self)
        if formatted_output:
            return pprint.pformat(raw)
        return raw

    def check_if_valid(self):
        """
        Raise exceptions if the object state is inconsistent.

        :raises CX: In case the name of the item is not set.
        """
        if not self.name:
            raise CX("Name is required")

    def make_clone(self):
        """
        Must be defined in any subclass
        """
        raise NotImplementedError("Must be implemented in a specific Item")

    @classmethod
    def _remove_depreacted_dict_keys(cls, dictionary: dict):
        """
        This method does remove keys which should not be deserialized and are only there for API compatibility in
        :meth:`~cobbler.items.item.Item.to_dict`.

        :param dictionary: The dict to update
        """
        if "ks_meta" in dictionary:
            dictionary.pop("ks_meta")
        if "kickstart" in dictionary:
            dictionary.pop("kickstart")

    def from_dict(self, dictionary: dict):
        """
        Modify this object to take on values in ``dictionary``.

        :param dictionary: This should contain all values which should be updated.
        :raises AttributeError: In case during the process of setting a value for an attribute an error occurred.
        :raises KeyError: In case there were keys which could not be set in the item dictionary.
        """
        result = copy.deepcopy(dictionary)
        for key in dictionary:
            lowered_key = key.lower()
            # The following also works for child classes because self is a child class at this point and not only an
            # Item.
            if hasattr(self, "_" + lowered_key):
                try:
                    setattr(self, lowered_key, dictionary[key])
                except AttributeError as error:
                    raise AttributeError(
                        f'Attribute "{lowered_key}" could not be set!'
                    ) from error
                result.pop(key)
        if len(result) > 0:
            raise KeyError(
                f"The following keys supplied could not be set: {result.keys()}"
            )

    def to_dict(self, resolved: bool = False) -> dict:
        """
        This converts everything in this object to a dictionary.

        :param resolved: If this is True, Cobbler will resolve the values to its final form, rather than give you the
                     objects raw value.
        :return: A dictionary with all values present in this object.
        """
        value = {}
        for key, key_value in self.__dict__.items():
            if key.startswith("_") and not key.startswith("__"):
                if key in (
                    "_conceptual_parent",
                    "_last_cached_mtime",
                    "_cached_dict",
                    "_supported_boot_loaders",
                ):
                    continue
                new_key = key[1:].lower()
                if isinstance(key_value, enum.Enum):
                    value[new_key] = key_value.value
                elif new_key == "interfaces":
                    # This is the special interfaces dict. Lets fix it before it gets to the normal process.
                    serialized_interfaces = {}
                    interfaces = key_value
                    for interface_key in interfaces:
                        serialized_interfaces[interface_key] = interfaces[
                            interface_key
                        ].to_dict()
                    value[new_key] = serialized_interfaces
                elif isinstance(key_value, list):
                    value[new_key] = copy.deepcopy(key_value)
                elif isinstance(key_value, dict):
                    if resolved:
                        value[new_key] = getattr(self, new_key)
                    else:
                        value[new_key] = copy.deepcopy(key_value)
                elif (
                    isinstance(key_value, str)
                    and key_value == enums.VALUE_INHERITED
                    and resolved
                ):
                    value[new_key] = getattr(self, key[1:])
                else:
                    value[new_key] = key_value
        if "autoinstall" in value:
            value.update({"kickstart": value["autoinstall"]})
        if "autoinstall_meta" in value:
            value.update({"ks_meta": value["autoinstall_meta"]})
        return value

    def serialize(self) -> dict:
        """
        This method is a proxy for :meth:`~cobbler.items.item.Item.to_dict` and contains additional logic for
        serialization to a persistent location.

        :return: The dictionary with the information for serialization.
        """
        keys_to_drop = [
            "kickstart",
            "ks_meta",
            "remote_grub_kernel",
            "remote_grub_initrd",
        ]
        result = self.to_dict()
        for key in keys_to_drop:
            result.pop(key, "")
        return result

    def deserialize(self, item_dict: dict):
        """
        This is currently a proxy for :py:meth:`~cobbler.items.item.Item.from_dict` .

        :param item_dict: The dictionary with the data to deserialize.
        """
        self.from_dict(item_dict)

    def grab_tree(self) -> list:
        """
        Climb the tree and get every node.

        :return: The list of items with all parents from that object upwards the tree. Contains at least the item
                 itself and the settings of Cobbler.
        """
        results = [self]
        parent = self.parent
        while parent is not None:
            results.append(parent)
            parent = parent.parent
            # FIXME: Now get the object and check its existence
        results.append(self.api.settings())
        self.logger.debug(
            "grab_tree found %s children (including settings) of this object",
            len(results),
        )
        return results
