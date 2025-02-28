# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0

"""The dispatch module contains classes inspirec by the visitor pattern in order
to allow to execute code specific to a certain object type but also allow to
have common code for all subclasses of a common parent class.

For each type of base class there is a sepearate \\*Dispatched class that are based
on the same principle.
If one wants to implement some code for a class, typically one subclasses the
corresponding dispatcher class and then overloads one of the methods to implement
class specific code. The method name to overload is based on the class name.
Code for a common parent class can be implement by only overloaded the corresponding
method for this common class without needing to overload each of the subclasses.
For multi-inheritance each of the super classes methods will be tried in order.
The dispatched for the base '_Shape' class will raise NotImplementedError if
not overloaded.

API Notes:
    * The multi-inheritance support is still done ad-hoc and may in the future
      be changed in a backwards incompatible way for code expecting certain
      order for calling parent classes.
"""
# TODO: think through dispatching for multi-inheritance

from .shape import *
from .primitive import *
from .rule import *
from .mask import *
from .edge import *