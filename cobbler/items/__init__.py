"""
This package contains all data storage classes. The classes are responsible for ensuring that types of the properties
are correct but not for logical checks. The classes should be as stupid as possible. Further they are responsible for
returning the logic for serializing and deserializing themselves.
"""
import copy
import logging
import re
import uuid
from typing import Union, TYPE_CHECKING, Type, Any, List

from cobbler import enums, utils
from cobbler.decorator import InheritableProperty

if TYPE_CHECKING:
    from cobbler.api import CobblerAPI


RE_OBJECT_NAME = re.compile(r"[a-zA-Z0-9_\-.:]*$")


class BaseItem:
    def __init__(self, api: "CobblerAPI"):
        self._ctime = 0.0
        self._mtime = 0.0
        self._uid = uuid.uuid4().hex
        self._name = ""
        self._comment = ""
        self._owners: Union[list, str] = enums.VALUE_INHERITED

        self.logger = logging.getLogger()
        self.api = api

    def __eq__(self, other):
        """
        Comparison based on the uid for our items.

        :param other: The other Item to compare.
        :return: True if uid is equal, otherwise false.
        """
        if isinstance(other, BaseItem):
            return self._uid == other.uid
        return False

    @property
    def uid(self) -> str:
        """
        The uid is the internal unique representation of a Cobbler object. It should never be used twice, even after an
        object was deleted.

        :getter: The uid for the item. Should be unique across a running Cobbler instance.
        :setter: The new uid for the object. Should only be used by the Cobbler Item Factory.
        """
        return self._uid

    @uid.setter
    def uid(self, uid: str):
        """
        Setter for the uid of the item.

        :param uid: The new uid.
        """
        self._uid = uid

    @property
    def ctime(self) -> float:
        """
        Property which represents the creation time of the object.

        :getter: The float which can be passed to Python time stdlib.
        :setter: Should only be used by the Cobbler Item Factory.
        """
        return self._ctime

    @ctime.setter
    def ctime(self, ctime: float):
        """
        Setter for the ctime property.

        :param ctime: The time the object was created.
        :raises TypeError: In case ``ctime`` was not of type float.
        """
        if not isinstance(ctime, float):
            raise TypeError("ctime needs to be of type float")
        self._ctime = ctime

    @property
    def mtime(self) -> float:
        """
        Represents the last modification time of the object via the API. This is not updated automagically.

        :getter: The float which can be fed into a Python time object.
        :setter: The new time something was edited via the API.
        """
        return self._mtime

    @mtime.setter
    def mtime(self, mtime: float):
        """
        Setter for the modification time of the object.

        :param mtime: The new modification time.
        """
        if not isinstance(mtime, float):
            raise TypeError("mtime needs to be of type float")
        self._mtime = mtime

    @property
    def name(self):
        """
        Property which represents the objects name.

        :getter: The name of the object.
        :setter: Updating this has broad implications. Please try to use the ``rename()`` functionality from the
                 corresponding collection.
        """
        return self._name

    @name.setter
    def name(self, name: str):
        """
        The objects name.

        :param name: object name string
        :raises TypeError: In case ``name`` was not of type str.
        :raises ValueError: In case there were disallowed characters in the name.
        """
        if not isinstance(name, str):
            raise TypeError("name must of be type str")
        if not RE_OBJECT_NAME.match(name):
            raise ValueError(f"Invalid characters in name: '{name}'")
        self._name = name

    @property
    def comment(self) -> str:
        """
        For every object you are able to set a unique comment which will be persisted on the object.

        :getter: The comment or an emtpy string.
        :setter: The new comment for the item.
        """
        return self._comment

    @comment.setter
    def comment(self, comment: str):
        """
        Setter for the comment of the item.

        :param comment: The new comment. If ``None`` the comment will be set to an emtpy string.
        """
        self._comment = comment

    @InheritableProperty
    def owners(self) -> list:
        """
        This is a feature which is related to the ownership module of Cobbler which gives only specific people access
        to specific records. Otherwise this is just a cosmetic feature to allow assigning records to specific users.

        .. warning:: This is never validated against a list of existing users. Thus you can lock yourself out of a
                     record.

        .. note:: This property can be set to ``<<inherit>>``.

        :getter: Return the list of users which are currently assigned to the record.
        :setter: The list of people which should be new owners. May lock you out if you are using the ownership
                 authorization module.
        """
        return self._resolve("owners")

    @owners.setter
    def owners(self, owners: Union[str, list]):
        """
        Setter for the ``owners`` property.

        :param owners: The new list of owners. Will not be validated for existence.
        """
        if not isinstance(owners, (str, list)):
            raise TypeError("owners must be str or list!")
        self._owners = self.api.input_string_or_list(owners)

    def _resolve(self, property_name: str) -> Any:
        """
        Resolve the ``property_name`` value in the object tree. This function traverses the tree from the object to its
        topmost parent and returns the first value that is not inherited. If the the tree does not contain a value the
        settings are consulted.

        :param property_name: The property name to resolve.
        :raises AttributeError: In case one of the objects try to inherit from a parent that does not have
                                ``property_name``.
        :return: The resolved value.
        """
        settings_name = property_name
        if property_name.startswith("proxy_url_"):
            property_name = "proxy"
        if property_name == "owners":
            settings_name = "default_ownership"
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)
        settings = self.api.settings()

        if attribute_value == enums.VALUE_INHERITED:
            if hasattr(settings, settings_name):
                return getattr(settings, settings_name)
            if hasattr(settings, f"default_{settings_name}"):
                return getattr(settings, f"default_{settings_name}")
            AttributeError(
                f'{type(self)} "{self.name}" inherits property "{property_name}", but neither its parent nor'
                f"settings have it"
            )

        return attribute_value

    def _resolve_enum(
        self, property_name: str, enum_type: Type[enums.ConvertableEnum]
    ) -> Any:
        """
        See :meth:`~cobbler.items.item.Item._resolve`
        """
        settings_name = property_name
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)
        settings = self.api.settings()

        if (
            isinstance(attribute_value, enums.ConvertableEnum)
            and attribute_value.value == enums.VALUE_INHERITED
        ):
            if hasattr(settings, settings_name):
                return enum_type.to_enum(getattr(settings, settings_name))
            if hasattr(settings, f"default_{settings_name}"):
                return enum_type.to_enum(getattr(settings, f"default_{settings_name}"))
            AttributeError(
                f'{type(self)} "{self.name}" inherits property "{property_name}", but neither its parent nor'
                "settings have it"
            )

        return attribute_value

    def _resolve_dict(self, property_name: str) -> dict:
        """
        Merge the ``property_name`` dictionary of the object with the ``property_name`` of all its parents. The value
        of the child takes precedence over the value of the parent.

        :param property_name: The property name to resolve.
        :return: The merged dictionary.
        :raises AttributeError: In case the the the object had no attribute with the name :py:property_name: .
        """
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)
        settings = self.api.settings()

        merged_dict = {}

        if hasattr(settings, property_name):
            merged_dict.update(getattr(settings, property_name))

        if attribute_value != enums.VALUE_INHERITED:
            merged_dict.update(attribute_value)

        utils.dict_annihilate(merged_dict)

        return merged_dict


class InheritableItem(BaseItem):
    def __init__(self, api: "CobblerAPI", is_subobject: bool = False):
        super().__init__(api)
        self._parent = ""
        self._depth = 0
        self._children = []
        self._conceptual_parent = None
        self._is_subobject = is_subobject

    @property
    def parent(self):
        """
        This property contains the name of the logical parent of an object. In case there is not parent this return
        None.

        :getter: Returns the parent object or None if it can't be resolved via the Cobbler API.
        :setter: The name of the new logical parent.
        """
        return None

    @parent.setter
    def parent(self, parent: str):
        """
        Set the parent object for this object.

        :param parent: The new parent object. This needs to be a descendant in the logical inheritance chain.
        """

    @property
    def children(self) -> List[str]:
        """
        The list of logical children of any depth.

        :getter: An empty list in case of items which don't have logical children.
        :setter: Replace the list of children completely with the new provided one.
        """
        return []

    @children.setter
    def children(self, value):
        """
        This is an empty setter to not throw on setting it accidentally.

        :param value: The list with children names to replace the current one with.
        """
        self.logger.warning(
            'Tried to set the children property on object "%s" without logical children.',
            self.name,
        )

    def get_children(self, sort_list: bool = False) -> List[str]:
        """
        Get the list of children names.

        :param sort_list: If the list should be sorted alphabetically or not.
        :return: A copy of the list of children names.
        """
        result = copy.deepcopy(self.children)
        if sort_list:
            result.sort()
        return result

    @property
    def descendants(self) -> list:
        """
        Get objects that depend on this object, i.e. those that would be affected by a cascading delete, etc.

        .. note:: This is a read only property.

        :getter: This is a list of all descendants. May be empty if none exist.
        """
        results = []
        kids = self.children
        for kid in kids:
            kid_item = self.api.find_items("", name=kid, return_list=False)
            grandkids = kid_item.descendants
            results.extend(grandkids)
        return results

    @property
    def is_subobject(self) -> bool:
        """
        Weather the object is a subobject of another object or not.

        :getter: True in case the object is a subobject, False otherwise.
        :setter: Sets the value. If this is not a bool, this will raise a ``TypeError``.
        """
        return self._is_subobject

    @is_subobject.setter
    def is_subobject(self, value: bool):
        """
        Setter for the property ``is_subobject``.

        :param value: The boolean value whether this is a subobject or not.
        :raises TypeError: In case the value was not of type bool.
        """
        if not isinstance(value, bool):
            raise TypeError(
                "Field is_subobject of object item needs to be of type bool!"
            )
        self._is_subobject = value

    @property
    def depth(self) -> int:
        """
        This represents the logical depth of an object in the category of the same items. Important for the order of
        loading items from the disk and other related features where the alphabetical order is incorrect for sorting.

        :getter: The logical depth of the object.
        :setter: The new int for the logical object-depth.
        """
        return self._depth

    @depth.setter
    def depth(self, depth: int):
        """
        Setter for depth.

        :param depth: The new value for depth.
        """
        if not isinstance(depth, int):
            raise TypeError("depth needs to be of type int")
        self._depth = depth

    def get_conceptual_parent(self):
        """
        The parent may just be a superclass for something like a subprofile. Get the first parent of a different type.

        :return: The first item which is conceptually not from the same type.
        """
        mtype = type(self)
        parent = self.parent
        while parent is not None:
            ptype = type(parent)
            if mtype != ptype:
                self._conceptual_parent = parent
                return parent
            parent = parent.parent
        return None

    def _resolve(self, property_name: str) -> Any:
        if property_name.startswith("proxy_url_"):
            property_name = "proxy"
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)

        if attribute_value == enums.VALUE_INHERITED:
            if self.parent is not None and hasattr(self.parent, property_name):
                return getattr(self.parent, property_name)
        return super()._resolve(property_name)

    def _resolve_enum(
        self, property_name: str, enum_type: Type[enums.ConvertableEnum]
    ) -> Any:
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)
        if (
            isinstance(attribute_value, enums.ConvertableEnum)
            and attribute_value.value == enums.VALUE_INHERITED
        ):
            if self.parent is not None and hasattr(self.parent, property_name):
                return getattr(self.parent, property_name)
        return super()._resolve_enum(property_name, enum_type)

    def _resolve_dict(self, property_name: str) -> dict:
        attribute = "_" + property_name

        if not hasattr(self, attribute):
            raise AttributeError(
                f'{type(self)} "{self.name}" does not have property "{property_name}"'
            )

        attribute_value = getattr(self, attribute)
        settings = self.api.settings()

        merged_dict = {}

        if self.parent is not None and hasattr(self.parent, property_name):
            merged_dict.update(getattr(self.parent, property_name))
        elif hasattr(settings, property_name):
            merged_dict.update(getattr(settings, property_name))

        if attribute_value != enums.VALUE_INHERITED:
            merged_dict.update(attribute_value)

        utils.dict_annihilate(merged_dict)

        return merged_dict
