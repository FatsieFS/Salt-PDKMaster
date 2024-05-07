# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""This module contains support for direct SPICE input and output.
"""
from typing import Dict, Optional, Union, overload, Any

from ...technology.primitive import (
    DevicePrimitiveT,
    Resistor, MIMCapacitor, Diode, MOSFET, Bipolar,
)


__all__ = ["SpicePrimParamsT", "SpicePrimsParamSpec"]


SpicePrimParamsT = Dict[str, Any]
class SpicePrimsParamSpec(Dict[DevicePrimitiveT, SpicePrimParamsT]):
    """``SpicePrimsParamSpec`` is a structure to declare extra parameters related
    to ``DevicePrimitiveT`` object of a technology that are needed specifically
    to generate SPICE/PySpice circuits.

    This class is used by first generating an empty object and then adding
    SPICE parameters for primitives using the ``add_device_params()`` method.
    """
    def __init__(self) -> None:  # We don't support arguments during creatinn of the object
        return super().__init__()

    def __setitem__(self, __key: DevicePrimitiveT, __value: SpicePrimParamsT) -> None:
        raise TypeError(
            "One must use add_device_params() method to add element to"
            " a SpicePrimsParamSpec object",
        )

    @overload
    def add_device_params(self, *,
        prim: Resistor, model: Optional[str]=None, is_subcircuit: Optional[bool]=False,
        subcircuit_paramalias: Optional[Dict[str, str]]=None,
        sheetres: Optional[float]=None,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: Union[MIMCapacitor, Diode], model: Optional[str]=None,
        is_subcircuit: Optional[bool]=True,
        subcircuit_paramalias: Optional[Dict[str, str]]=None,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: MOSFET, model: Optional[str]=None,
        is_subcircuit: Optional[bool]=False,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: Bipolar, model: Optional[str]=None, is_subcircuit: Optional[bool]=False,
    ):
        ... # pragma: no cover
    def add_device_params(self, *,
        prim: DevicePrimitiveT, model: Optional[str]=None,
        is_subcircuit: Optional[bool]=None,
        **params: Any,
    ):
        """The ``add_device_params()`` method is called at most once for each device
        primitive one wants to add params for. The params that can be specified depend
        on the device primitive type.

        Parameters:
            model:
                alternative model name for use in SPICE circuit.

                By default the name of the primitive is also used as the SPICE model
                name
            is_subcircuit:
                wether the model is a SPICE subcircuit or element

                Default is ``True`` for a ``MIMCapacitor`` and ``False`` for the other
                device primitives.
            subcircuit_paramalias (for ``Resistor``, ``MIMCapacitor`` and ``Diode``):
                alias for parameters for the subcircuit model.

                This value is a dict that specifies the alias for the parameters of the
                primitive. The keys the names of the parameter for the ``DevicePrimitiveT``
                the values the name of the parameter used by the SPICE subcircuit.

                Either no parameter has to be specified are all of them. It may not be
                specified when ``is_subcircuit`` is ``False``.

                Default values:

                * for ``Resistor``: ``{"width": "w", "length": "l"}``,
                * for ``MIMCapacitor``: ``{"width": "w", "height": "h"}``,
                * for ``Diode``: ``{"width": "w", "height": "h"}``,

            sheetres (for ``Resistor``):
               the sheet resistance for the ``Resistor`` primitive
        """
        if is_subcircuit is None:
            if isinstance(prim, MIMCapacitor):
                is_subcircuit = True
            else:
                is_subcircuit = False
        params["is_subcircuit"] = is_subcircuit

        if isinstance(prim, (Resistor, MIMCapacitor, Diode)):
            # handle subcircuit_paramalias parameter
            subcircuit_paramalias: Optional[Dict[str, str]] = params.get("subcircuit_paramalias", None)
            if subcircuit_paramalias is not None:
                if not is_subcircuit:
                    raise ValueError(
                        "subcircuit_paramalias specified with is_subcircuit `False`",
                    )
                keys = (
                    {"width", "length"} if isinstance(prim, Resistor)
                    else {"width", "height"}
                )
                if set(subcircuit_paramalias.keys()) != keys:
                    raise ValueError(
                        f"subcircuit_paramalias has to be None or a dict with keys {keys}"
                    )
            params["subcircuit_paramalias"] = subcircuit_paramalias

        if isinstance(prim, Resistor):
            # handle sheetres param
            params["sheetres"] = params.get("sheetres", None)

        if model is None:
            if isinstance(prim, Resistor):
                # For a Resistor primitive, model name may be None if sheetres is specified.
                if params["sheetres"] is None:
                    model = prim.name
                else:
                    if params["subcircuit_paramalias"] is not None:
                        raise TypeError(
                            "subcircuit_paramalias provided without a model for Resistor"
                            f" '{prim.name}'"
                        )
            else:
                # For other primitives use the primitive name as model name if it was not
                # specified
                model = prim.name
        params["model"] = model

        super().__setitem__(prim, params)
