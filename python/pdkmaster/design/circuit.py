# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Union, Optional, Iterable, Any, overload

from pdkmaster.typing import OptMultiT

from .. import _util
from ..technology import net as _net, primitive as _prm, technology_ as _tch


__all__ = [
    "InstanceT", "InstancesT", "InstanceNetT", "InstanceNetsT",
    "PrimitiveInstanceT", "CellInstanceT",
    "CircuitNetT", "CircuitNetsT",
    "CircuitT", "CircuitsT",
    "CircuitFactory",
]


class _Instance(abc.ABC):
    """Base classes representing an instance in a _Circuit.

    Instances in a circuit are created with the `_Circuit.instantiate()` method.
    Arguments to use are given in the docs of that method.

    Attributes:
        ports: the ports of this instances.
    """
    @abc.abstractmethod
    def __init__(self, *, name: str, ports: "InstanceNetsT"):
        self.name = name
        ports._freeze_()
        self.ports = ports
InstanceT = _Instance


class _InstanceNet(_net._Net):
    """Internal `_Instance` support class"""
    def __init__(self, *, inst: InstanceT, net: _net.NetT):
        super().__init__(net.name)
        self.inst = inst
        self.net = net
        self.full_name = f"{inst.name}.{net.name}"

    def __hash__(self) -> int:
        return hash(self.full_name)

    def __eq__(self, other) -> bool:
        return isinstance(other, _InstanceNet) and ((self.full_name) == other.full_name)
InstanceNetT = _InstanceNet


class _InstanceNets(_util.ListStrMappingOverride[_InstanceNet], _net.Nets):
    """Internal `_Instance` support class"""
    # TODO: Make sure only nets from the same instance are added
    pass
InstanceNetsT = _InstanceNets


class _Instances(_util.ExtendedListStrMapping[_Instance]):
    pass
InstancesT = _Instances


class _PrimitiveInstance(_Instance):
    """Internal `_Instance` support class"""
    def __init__(self, *, name: str, prim: _prm.DevicePrimitiveT, **params: Any):
        self.name = name
        super().__init__(
            name=name, ports=_InstanceNets(
                (_InstanceNet(inst=self, net=port) for port in prim.ports),
            )
        )

        self.prim = prim
        self.params = params
PrimitiveInstanceT = _PrimitiveInstance


class _CellInstance(_Instance):
    """Internal `_Instance` support class"""
    def __init__(self, *,
        name: str, cell: "_cell.Cell", circuitname: Optional[str]=None,
    ):
        self.name = name
        self.cell = cell

        if circuitname is None:
            try:
                circuit = self.cell.circuit
            except AttributeError: # pragma: no cover
                raise TypeError(
                    "no circuitname provided for cell without default circuit"
                )
        else:
            circuit = cell._circuits[circuitname]
        self.circuitname = circuitname
        self.circuit: CircuitT = circuit

        super().__init__(
            name=name, ports=_InstanceNets(
                (_InstanceNet(inst=self, net=port) for port in circuit.ports),
            ),
        )
CellInstanceT = _CellInstance


class _CircuitNet(_net._Net):
    """A net in a `_Circuit` object.
    It needs to be generated with the `_Circuit.new_net()` method.

    Nets in a circuit are created with the `_Circuit.new_net()` method.
    Arguments to use are given in the docs of that method.

    Attributes:
        circuit: the circuit to which this net belongs
        childports: the ports of the instances that are connected by this net
            See `_Circuit.new_net()` docs on how to populate this collection
        external: wether this is an external net; e.g. a port of the circuit
    """
    def __init__(self, *,
        circuit: "CircuitT", name: str, external: bool,
    ):
        super().__init__(name)
        self.circuit = circuit
        self.childports: InstanceNetsT = _InstanceNets()
        self.external = external

    def freeze(self) -> None:
        self.childports._freeze_()
CircuitNetT = _CircuitNet


class _CircuitNets(_util.ListStrMappingOverride[_CircuitNet], _net.Nets):
    """Internal `_Circuit` support class"""
    _elem_type = _CircuitNet
CircuitNetsT = _CircuitNets


class _Circuit:
    """A circuit consists of instances of subelements and nets to connect
    ports of the instances. Nets can be external and nets are then ports
    that can be used in hierarchically instantiated cells.

    New circuits are created with the `CircuitFactory.new_circuit()` method.
    Arguments to use are given in the docs of that method.

    Arguments:
        instances: the instances of this circuit
        nets: the nets of this circuit
        porrts: the ports of this circuit; e.g. the external nets
    """
    def __init__(self, *, name: str, fab: "CircuitFactory"):
        self.name = name
        self.fab = fab

        self.instances: InstancesT = _Instances()
        self.nets: CircuitNetsT = _CircuitNets()
        self.ports: CircuitNetsT = _CircuitNets()

    @overload
    def instantiate(self,
        object_: _prm.DevicePrimitiveT, *, name: str, **params,
    ) -> PrimitiveInstanceT:
        ... # pragma: no cover
    @overload
    def instantiate(self,
        object_: "_cell.Cell", *, name: str, **params,
    ) -> CellInstanceT:
        ... # pragma: no cover
    def instantiate(self, object_: Union[_prm.DevicePrimitiveT, "_cell.Cell"], *,
        name: str, **params,
    ) -> InstanceT:
        """Instantiate an element in a circuit.

        Arguments:
            object_: the element to instantiate
                Currently a `DevicePrimitiveT` object or a `_Cell` object are supported.
                Conductors are not added to the circuit but added to the layout using the
                `add_wire()` method.
            name: name of the instance
                This name can used to access the instance from the `instances`
                attribute.
            params: the params for the instance.
                Currently params are only support when instantiating a `_Primitive`.
                Parametric circuit are currently not supported.
        """
        if isinstance(object_, _prm.DevicePrimitiveT):
            params = object_.cast_params(params)
            inst = _PrimitiveInstance(name=name, prim=object_, **params)
        elif isinstance(object_, _cell.Cell):
            circuitname = params.pop("circuitname", None)
            if params: # pragma: no cover
                raise NotImplementedError("Parametric Circuit instance")
            inst = _CellInstance(name=name, cell=object_, circuitname=circuitname)
        else:
            raise TypeError(
                f"object_ has to be of type '_Primitive' or '_Cell', not {type(object_)}",
            )

        self.instances += inst
        return inst

    def new_net(self, *,
        name: str, external: bool, childports: OptMultiT[_InstanceNet]=None,
    ) -> CircuitNetT:
        """Create a new net in a circuit.

        Arguments:
            name: the name of the net
            external: wether this is an external net; e.g. a port of this circuit
            childports: the ports of instances in this class that are connected
                by this nets.
                A strategy is to first instantiate all elements in a circuit and then
                pass the ports for the nets during circuit generation. Alternative
                is to not specify it during net creation but add ports to `childports`
                attribute when one goes along. Or a combination of both.
        """
        net = _CircuitNet(circuit=self, name=name, external=external)
        self.nets += net
        if external:
            self.ports += net
        if childports:
            net.childports += childports
        return net

    @property
    def subcells_sorted(self) -> Iterable["_cell.Cell"]:
        """Return sorted iterable of the hierarchical cell instantiation.
        The cells will be sorted such that a cell is in the list before a
        cell where it is instantiated.

        Main use of this attribute will be for the `Library.subcells_sorted`
        attribute.
        """
        cells = set()
        for inst in self.instances.__iter_type__(_CellInstance):
            if inst.cell not in cells:
                for subcell in inst.cell.subcells_sorted:
                    if subcell not in cells:
                        yield subcell
                        cells.add(subcell)
                yield inst.cell
                cells.add(inst.cell)

    def net_lookup(self, *, port: "InstanceNetT") -> "CircuitNetT":
        """Look up to which net a instance port belongs.

        Arguments:
            port: the port to look up
        """
        for net in self.nets:
            for childport in net.childports:
                if (childport.inst == port.inst) and (childport.name == port.name):
                    return net
        else:
            raise ValueError(
                f"Net for port {port.name} of instance {port.inst.name} not found",
            )
CircuitT = _Circuit


class _Circuits(_util.ExtendedListStrMapping[_Circuit]):
    pass
CircuitsT = _Circuits


class CircuitFactory:
    """The user facing class for creating circuits. This class is also a base
    class on which own factory classes can be built with specific extensions.

    Parameters:
        tech: the technology for which to create circuits. Created circuits may
            only contain instances from primitives from this technology.

    API Notes:
        The contract for making subclasses has not been finaziled. Backwards
            incompatible changes are still expected for subclasses of this class.
    """
    def __init__(self, *, tech: _tch.Technology):
        self.tech = tech

    def new_circuit(self, *, name: str) -> CircuitT:
        """Create a circuit.

        This method is the user facing API to generate circuits.
        Returns a `_Circuit` object; see docs for that class on user facing API
        for that class.
        """
        return _Circuit(name=name, fab=self)


# Imported at end to handle recursive imports
from . import cell as _cell
