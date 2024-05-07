# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from ... import _util
from .skill_grammar import SkillFile, _skill_functionlist


__all__ = ["TechFile"]


#
# Technology file support functions
#
def _get_layername(v):
    """Get layer name. Value can be a string or a list of two values for layer purpose
    If purpose is specified it will return a layer name using '.' as delimiter between layername
    and purpose
    """
    if isinstance(v, str):
        return _util.strip_literal(v)
    elif len(v) == 1:
        return _util.strip_literal(v[0])
    elif len(v) == 2:
        return _util.strip_literal(v[0])+"."+_util.strip_literal(v[1])
    else:
        raise ValueError("{!r} is not a valid layer specification")


def _get_bool(v):
    assert type(v) is bool
    return v


def _get_combinedlayername(v):
    """Returns a combination of layers, the layers will be separated by a ':' as delimiter.

    This is used for layer pair for design rules or for a triple of layers for via rule"""
    assert len(v) > 1
    return ":".join([_get_layername(elem) for elem in v])


def _get_numornil(v):
    if isinstance(v, bool):
        assert not v
        return None
    else:
        assert isinstance(v, (int, float))
        return v


def _prop_value(elems, **kwargs):
    ret = {}
    for v in elems:
        assert 2 <= len(v) <= 4
        prop = _util.strip_literal(v[0])
        value = v[1]
        ret[prop] = value
        if len(v) > 2:
            prop += "."+v[2]
            value = v[3] if len(v) > 3 else True
            ret[prop] = value

    return ret


def _prop_layers_value_optextra(elems, **kwargs):
    """data: [prop (layer1 (layer2 (layer3))) value (extraprop (extravalue))]
    if no layer is present "_" will be used for layername"""
    ret = {}
    for v in elems:
        cond = v[0]
        if len(v) == 2:
            layer = "_"
            spec = v[1]
            extra = None
        else:
            end = 2
            while (
                ((type(v[end]) is str) and v[end][0] != "'")
                or ((type(v[end]) is list) and (type(v[end][0]) is str))
            ):
                end += 1
            if end == 2:
                layer = _get_layername(v[1])
            else:
                layer = _get_combinedlayername(v[1:end])
            spec = v[end]
            if len(v) > end+1:
                extra = cond + "." + v[end+1]
                extra_spec = v[end+2] if len(v) > end+2 else True
            else:
                extra = None
        if layer in ret:
            ret[layer][cond] = spec
        else:
            ret[layer] = {cond: spec}
        if extra:
            ret[layer][extra] = extra_spec

    return ret


def _prop_cumulative_value(elems, *, functionname, **kwargs):
    d = {}
    for v in elems:
        cond = v[0]
        if functionname == "cumulativeMetalAntenna":
            cond += ".cumulative_metal"
        elif functionname == "cumulativeViaAntenna":
            cond += ".cumulative_via"
        else:
            raise Exception(f"unhandled name '{functionname}'")
        d[cond] = v[1]
        if len(v) > 2:
            d[cond + "." + v[2]] = True if len(v) == 3 else v[3]

    return {"_": d}


def _prop_value_units(elems, **kwargs):
    ret = {}
    for prop, units, value in elems:
        ret[prop] = [value, units]

    return ret


def _layer_value(elems, *, unique=False, **kwargs):
    ret = {}
    for layer, value in elems:
        layername = _get_layername(layer)
        if unique:
            assert layername not in ret
        ret[layername] = value

    return ret


def _layer_values(elems, **kwargs):
    ret = {}
    for v in elems:
        ret[_get_layername(v[0])] = v[1:]

    return ret


def _layers(elems, **kwargs):
    return [_get_layername(elem) for elem in elems]


def _combinedlayers(elems, **kwargs):
    return [_get_combinedlayername(elem) for elem in elems]


def _techParams(elems, **kwargs):
    ret = {}
    for v in elems:
        assert len(v) == 2
        paramname = v[0]
        if paramname.endswith("layer") | paramname.endswith("Layer"):
            ret[paramname] = _get_layername(v[1])
        elif paramname.endswith("layers"):
            if not isinstance(v[1], bool):
                ret[paramname] = [_get_layername(layer) for layer in v[1]]
            else:
                assert not v[1]
        else:
            ret[v[0]] = v[1]

    return ret


def _name_abbreviation(elems, **kwargs):
    ret = {}
    for v in elems:
        assert len(v) in (2, 3)
        techname = v[0]
        d = {"number": v[1]}
        if len(v) > 2:
            d["abbreviation"] = v[2]
        ret[techname] = d

    return ret


def _techDisplays(elems, **kwargs):
    ret = {}
    for v in elems:
        layername = _get_layername(v[0:2])
        ret[layername] = {
            "packet": v[2],
            "visible": _get_bool(v[3]),
            "selectable": _get_bool(v[4]),
            "con2chgly": _get_bool(v[5]),
            "drawable": _get_bool(v[6]),
            "valid": _get_bool(v[7]),
        }

    return ret


def _standardViaDefs(elems, **kwargs):
    ret = []
    for v in elems:
        d = {
            "name": v[0],
            "layer1": {
                "name": _get_layername(v[1]),
                "enclosure": v[5],
                "offset": v[7],
            },
            "via": {
                "name": _get_layername(v[3][0]),
                "width": v[3][1],
                "height": v[3][2],
                "rows": v[4][0],
                "cols": v[4][1],
            },
            "layer2": {
                "name": _get_layername(v[2]),
                "enclosure": v[6],
                "offset": v[8],
            },
            "offset": v[9],
        }
        if len(v[3]) > 3:
            d["via"]["resistance"] = v[3][3]
        if len(v[4]) > 2:
            d["via"]["space"] = v[4][2]
        if len(v[4]) > 3:
            d["via"]["pattern"] = v[4][3]
        if (len(v) > 10) and v[10]:
            d["layer1"]["implant"] = {
                "name": _get_layername(v[10]),
                "enclosure": v[11],
            }
        if len(v) > 12:
            d["layer2"]["implant"] = {
                "name": _get_layername(v[12]),
                "enclosure": v[13],
            }
            if len(v) > 14:
                d["well"] = v[14]

        ret.append(d)

    return ret


def _customViaDefs(elems, **kwargs):
    ret = {}
    for v in elems:
        vianame = v[0]
        assert vianame not in ret
        ret[vianame] ={
            "library": v[1],
            "cell": v[2],
            "view": v[3],
            "layer1": _get_layername(v[4]),
            "layer2": _get_layername(v[5]),
            "resistance": v[6],
        }

    return ret


def _spacingTables(elems, **kwargs):
    ret = {}
    for v in elems:
        if isinstance(v[2], list):
            layer = _get_layername(v[1])
            define = v[2]
            table = v[3]
            tail = v[4:]
        elif len(v) > 4:
            layer = _get_combinedlayername(v[1:3])
            define = v[3]
            table = v[4]
            tail = v[5:]
        else:
            raise ValueError("Unexpected spacingTables length")
        assert len(define[0]) == 3 or len(define[0]) == 6
        assert not define[0][1] and not define[0][2]

        d = {
            "index": define[0][0],
        }

        if len(define[0]) > 3:
            assert not define[0][4] and not define[0][5]
            d["index2"] = define[0][3]
        if len(define) > 1:
            d["default"] = define[1]
        if len(define[0]) == 3:
            d["table"] = [[table[2*i], table[2*i+1]] for i in range(len(table)//2)]
        else: # len(define[0]) == 6
            d["table"] = [[*table[2*i], table[2*i+1]] for i in range(len(table)//2)]

        if len(tail) == 1:
            d[tail[0]] = True
        elif len(tail) > 1:
            d[tail[0]] = tail[1]

        if layer in ret:
            ret[layer][v[0]] = d
        else:
            ret[layer] = {v[0]: d}

    return ret


def _viaSpecs(elems, **kwargs):
    ret = {}
    for v in elems:
        layer = _get_combinedlayername(v[0:2])
        if len(v[2]) == 1:
            vias = v[2][0]
        else:
            vias = v[2]
        ret[layer] = vias

    return ret


def _antennaModels(elems, **kwargs):
    ret = {}
    for v in elems:
        modelname = v[0]
        rules = {}
        for rule in v[1:]:
            for rulename, spec in rule.items():
                if rulename == "antenna":
                    v2 = _prop_layers_value_optextra(spec, functionname=rulename)
                elif rulename in ("cumulativeMetalAntenna", "cumulativeViaAntenna"):
                    v2 =  _prop_cumulative_value(spec, functionname=rulename)
                else:
                    raise ValueError(f"Unsupported rulename '{rulename}' for antenneModels")
                for layer, layerspec in v2.items():
                    if layer in rules:
                        rules[layer].update(layerspec)
                    else:
                        rules[layer] = layerspec
        ret[modelname] = rules

    return ret


def _constraintGroups(elems, **kwargs):
    ret = {}
    for v in elems:
        groupname = _util.strip_literal(v[0])
        override = _get_bool(v[1])
        constraints = {"override": override}
        if (len(v) > 2) and isinstance(v[2], str):
            constraints["abbreviation"] = v[2]
            start = 3
        else:
            start = 2
        for constraint in v[start:]:
            for rulename, rules in constraint.items():
                if rulename in constraints:
                    c2 = constraints[rulename]
                    def add2layer(rule):
                        layer, spec = rule
                        if layer in c2:
                            c2[layer].update(spec)
                            return True
                        else:
                            return False
                    c2.update(filter(
                        lambda r: not add2layer(r), rules.items(),
                    ))
                else:
                    constraints[rulename] = rules

        # Convert spacings, orderedSpacings, spacingTables, routingGrids, antennaModels -> rules
        layerrules = constraints.pop("spacings", {})

        # Add specified groups, optionally transforming the rule name
        def _add_table(name):
            if name.endswith(".ref"):
                name[-4:] = ".table.ref"
            else:
                name += ".table"
            return name
        group_spec = [
            ("orderedSpacings", lambda name: name),
            ("electrical", lambda name: name),
            ("spacingTables", _add_table),
            ("routingGrids", lambda name: "routing."+name),
        ]
        for subgroupname, nametrans in group_spec:
            for layer, addrules in constraints.pop(subgroupname, {}).items():
                # Remove minEnclosure if exist minOppExtension with same minimal enclosure
                if ((subgroupname == "orderedSpacings") and ("minEnclosure" in addrules) and ("minOppExtension" in addrules)):
                    if addrules["minEnclosure"] == addrules["minOppExtension"][0]:
                        addrules.pop("minEnclosure")
                rules = layerrules.get(layer, {})
                rules.update({nametrans(rulename): data for rulename, data in addrules.items()})
                layerrules[layer] = rules

        # Add antennaModels -> rules; append antenna model name if not default
        for modelname, models in constraints.pop("antennaModels", {}).items():
            modelsuffix = "" if modelname == "default" else "."+modelname
                
            for layer, arules in models.items():
                rules = layerrules.get(layer, {})
                rules.update({rulename+modelsuffix: data for rulename, data in arules.items()})
                layerrules[layer] = rules

        if layerrules:
            constraints["rules"] = layerrules
        
        ret[groupname] = constraints

    return ret


def _techDerivedLayers(elems, **kwargs):
    ret = {}
    for v in elems:
        assert len(v) == 3 and len(v[2]) == 3
        if isinstance(v[2][2], (int, float)):
            ret[v[0]] = {
                "number": v[1],
                "layer": _get_layername(v[2][0]),
                v[2][1]: v[2][2],
            }
        else:
            ret[v[0]] = {
                "number": v[1],
                "layer": _get_combinedlayername([v[2][0], v[2][2]]),
                "operation": v[2][1],
            }

    return ret


def _functions(elems, **kwargs):
    ret = {}
    for v in elems:
        assert 2 <= len(v) <= 3
        layer = _get_layername(v[0])
        assert layer not in ret
        ret[layer] = {"function": _util.strip_literal(v[1])}
        if len(v) > 2:
            ret[layer]["mask_number"] = v[2]

    return ret


def _multipartPathTemplates(elems, **kwargs):
    ret = {}
    for v in elems:
        assert len(v) == 5

        pathname = v[0]

        v2 = v[1]
        l = len(v2)
        assert 1 <= l <= 9
        d = {"layer": _get_layername(v2[0])}
        if l > 1:
            d["width"] = v2[1]
        if l > 2:
            d["choppable"] = _get_bool(v2[2])
        if l > 3:
            d["endtype"] = v2[3]
        if l > 4:
            d["begin_extension"] = v2[4]
        if l > 5:
            d["end_extension"] = v2[5]
        if l > 6:
            d["justify"] = _get_bool(v2[6])
        if l > 7:
            d["offset"] = v2[7]
        if l > 8:
            d["connectivity"] = v2[8]
        spec = {"master": d}

        v2 = v[2]
        if not isinstance(v2, bool):
            subpaths = []
            for v3 in v2:
                l = len(v3)
                assert 1 <= l <= 8
                d = {"layer": _get_layername(v3[0])}
                if l > 1:
                    d["width"] = v3[1]
                if l > 2:
                    d["choppable"] = _get_bool(v3[2])
                if l > 3:
                    d["separation"] = v3[3]
                if l > 4:
                    d["justification"] = v3[4]
                if l > 5:
                    d["begin_offset"] = v3[5]
                if l > 6:
                    d["end_offset"] = v3[6]
                if l > 7:
                    d["connectivity"] = v3[7]
                subpaths.append(d)
                spec["offset"] = subpaths
        else:
            assert not v2

        v2 = v[3]
        if not isinstance(v2, bool):
            subpaths = []
            for v3 in v2:
                l = len(v3)
                assert 1 <= l <= 7
                d = {"layer": _get_layername(v3[0])}
                if l > 1:
                    d["enclosure"] = v3[1]
                if l > 2:
                    d["choppable"] = _get_bool(v3[2])
                if l > 3:
                    d["separation"] = v3[3]
                if l > 4:
                    d["begin_offset"] = v3[4]
                if l > 5:
                    d["end_offset"] = v3[5]
                if l > 6:
                    d["connectivity"] = v3[6]
                subpaths.append(d)
            spec["enclosure"] = subpaths
        else:
            assert not v2

        v2 = v[4]
        if not isinstance(v2, bool):
            subpaths = []
            for v3 in v2:
                l = len(v3)
                assert 1 <= l <= 13
                d = {"layer": _get_layername(v3[0])}
                if l > 1:
                    n = _get_numornil(v3[1])
                    if n is not None:
                        d["width"] = n
                if l > 2:
                    n = _get_numornil(v3[2])
                    if n is not None:
                        d["length"] = n
                if l > 3:
                    d["choppable"] = _get_bool(v3[3])
                if l > 4:
                    d["separation"] = v3[4]
                if l > 5:
                    d["justification"] = v3[5]
                if l > 6:
                    n = _get_numornil(v3[6])
                    if n is not None:
                        d["space"] = n
                if l > 7:
                    d["begin_offset"] = v3[7]
                if l > 8:
                    d["end_offset"] = v3[8]
                if l > 9:
                    d["gap"] = v3[9]
                if l > 10:
                    c = v3[10]
                    if not (isinstance(c, bool) and not c):
                        d["connectivity"] = c
                if l > 11:
                    n = _get_numornil(v3[11])
                    if n is not None:
                        d["begin_segoffset"] = n
                if l > 12:
                    n = _get_numornil(v3[12])
                    if n is not None:
                        d["end_segoffset"] = n
                subpaths.append(d)
            spec["rects"] = subpaths

        ret[pathname] = spec

    return ret


def _streamLayers(elems, **kwargs):
    ret = {}
    for layer, number, datatype, translate in elems:
        layername = _get_layername(layer)
        ret[layername] = {
            "number": number,
            "datatype": datatype,
            "translate": _get_bool(translate),
        }

    return ret


def _layerFunctions(elems, **kwargs):
    ret = {}
    for v in elems:
        assert 2 <= len(v) <= 3
        layername = _get_layername(v[0])
        d = {"function": v[1]}
        if len(v) > 2:
            d["masknumber"] = v[2]
        assert layername not in ret
        ret[layername] = d

    return ret


def _spacingRules(elems, **kwargs):
    ret = {}
    for v in elems:
        specname = v[0]
        assert 3 <= len(v) <= 4
        if len(v) == 3:
            layername = _get_layername(v[1])
        elif len(v) == 4:
            layername = _get_combinedlayername(v[1:3])
        specvalue = v[-1]
        if layername in ret:
            ret[layername][specname] = specvalue
        else:
            ret[layername] = {specname: specvalue}

    return ret


def _layerDefinitions(elems, **kwargs):
    class _LookupExtend():
        def __init__(self, data):
            self.data = data
            self.newidx = -1
        
        def __getitem__(self, item):
            try:
                return self.data[item]
            except KeyError:
                self.data[item] = value = {"number": self.newidx}
                self.newidx -= 1
                return value

    d_elems = {}
    for elem in elems:
        assert isinstance(elem, dict) and len(elem) == 1
        d_elems.update(elem)

    techlayers = _LookupExtend(d_elems.pop("techLayers"))
    techpurposes = _LookupExtend(d_elems.pop("techPurposes"))
    techlayerpurposes = d_elems.pop("techLayerPurposePriorities")
    techdisplays = d_elems.pop("techDisplays")
    techlayerproperties = d_elems.pop("techLayerProperties", {})
    assert set(techlayerpurposes) == set(techdisplays.keys())

    def _layerpurpose2value(name):
        lname, pname = name.split('.')
        ldata = techlayers[lname]
        labbr = ldata.get("abbreviation")
        if labbr == lname:
            labbr = None
        pdata = techpurposes[pname]
        pabbr = pdata.get("abbreviation")
        if pabbr == pname:
            pabbr = None

        aliases = []
        if pname == "drawing":
            aliases.append(lname)
        if labbr and (labbr != lname):
            aliases.append(".".join((labbr, pname)))
            if pabbr and (pabbr != pname):
                aliases.append(".".join((labbr, pabbr)))
        if pabbr and (pabbr != pname):
            aliases.append(".".join((lname, pabbr)))

        value = {
            "name": name,
            "aliases": aliases,
            "layer": ldata["number"],
            "purpose": pdata["number"],
        }
        value.update(techdisplays[name])
        for name_it in [name] + aliases:
            value.update(techlayerproperties.pop(name_it, {}))
        return value

    d_elems["layers"] = [_layerpurpose2value(layerpurpose) for layerpurpose in techlayerpurposes]
    assert len(techlayerproperties) == 0, f"Remaining layerproperties: {list(techlayerproperties.keys())}"
    return d_elems


_value4function_table = {
    "techLayerPurposePriorities": _layers,
    "controls": _skill_functionlist,
    "interconnect": _prop_value,
    "viewTypeUnits": _prop_value_units,
    "viaLayers": _combinedlayers,
    "routingGrids": _prop_layers_value_optextra,
    "spacings": _prop_layers_value_optextra,
    "orderedSpacings": _prop_layers_value_optextra,
    "electrical": _prop_layers_value_optextra,
    "orderedElectrical": _prop_layers_value_optextra,
    "techLayerProperties": _prop_layers_value_optextra,
    "characterizationRules": _prop_layers_value_optextra,
    "currentDensity": _prop_layers_value_optextra,
    "routingDirections": _layer_value,
    "stampLabelLayers": _layer_values,
    "compactorLayers": (_layer_value, {"unique": True}),
    "techPurposes": _name_abbreviation,
    "techLayers": _name_abbreviation,
    "techParams": _techParams,
    "techDisplays": _techDisplays,
    "standardViaDefs": _standardViaDefs,
    "customViaDefs": _customViaDefs,
    "viaDefs": _skill_functionlist,
    "spacingTables": _spacingTables,
    "viaSpecs": _viaSpecs,
    "antennaModels": _antennaModels,
    "constraintGroups": _constraintGroups,
    "techDerivedLayers": _techDerivedLayers,
    "functions": _functions,
    "multipartPathTemplates": _multipartPathTemplates,
    "streamLayers": _streamLayers,
    "layerFunctions": _layerFunctions,
    "spacingRules": _spacingRules,
    "orderedSpacingRules": _spacingRules,
    "layerRules": _skill_functionlist,
    "layerDefinitions": _layerDefinitions,
    # Following functions are not directly converted but done inside antennaModels function
    # "antenna": _prop_layers_value_optextra,
    # "cumulativeMetalAntenna": _prop_cumulative_value,
    # "cumulativeViaAntenna": _prop_cumulative_value,
}


#
# Grammar
#
class TechFile(SkillFile):
    def grammar_elem_init(self, sessiondata):
        super().grammar_elem_init(sessiondata)
        self.ast = {"TechFile": self.ast["SkillFile"]}
        newvalue = {}

        layerrules = {}
        for v in self.value["SkillFile"]:
            if ("layerDefinitions" in v) and ("layers" in v["layerDefinitions"]):
                layers = v["layerDefinitions"].pop("layers")
                layers_idx = {layer["name"]: layer for layer in layers}
                for alias_idx in [{alias: layer for alias in layer["aliases"]} for layer in layers]:
                    layers_idx.update(alias_idx)
                newvalue["layers"] = {
                    "list": layers,
                }
                # Add remaining fields if present
                if v["layerDefinitions"]:
                    newvalue.update(v)
            elif ("layerRules" in v):
                assert len(v) == 1
                layerrules = v["layerRules"]
            else:
                newvalue.update(v)

        # Process layerrules
        # Filter out empty fields
        layerrules = dict(filter(lambda item: item[1], layerrules.items()))
        if "equivalentLayers" in layerrules:
            newvalue["layers"]["equivalent"] = layerrules.pop("equivalentLayers")
        for layername, fdata in layerrules.pop("functions", {}).items():
            layers_idx[layername].update(fdata)
        for layername, direction in layerrules.pop("routingDirections", {}).items():
            layers_idx[layername]["direction"] = direction
        if layerrules:
            newvalue.update({"layerRules": layerrules})

        # Add connects section based on via section
        try:
            defs = newvalue["viaDefs"]["standardViaDefs"]
        except KeyError:
            pass
        else:
            newvalue["connects"] = list({
                "{}:{}:{}".format(
                    viadef["layer1"]["name"], viadef["via"]["name"], viadef["layer2"]["name"]
                ) for viadef in defs
            })

        self.value = newvalue

    @classmethod
    def parse_string(cls, text):
        return super().parse_string(
            text, value4funcs=_value4function_table, dont_convert=["currentDensity"]
        )
