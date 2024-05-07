# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from ... import _util
from .skill_grammar import SkillFile, SkillContext, SkillInterpreter, _skill_if


__all__ = ["AssuraFile", "AssuraInterpreter"]


#
# Script interpretation support classes
#
class LayerDef(dict):
    def __repr__(self):
        s = self['df2']
        if s.startswith("layer:"):
            s = s[6:]
        return s


class DRCExtractContext(SkillContext):
    def __init__(self, context):
        super().__init__(parent=context)
        self.rules = []
        self.extracts = {}


class LayerOperation:
    binops = {
        "geomAnd": "&",
        "geomAndNot": "-",
        "geomOr": "|",
    }

    def __init__(self, operation, args):
        self.operation = operation
        self.args = args
        self.name = None

    def __str__(self):
        def str_conv(arg):
            if hasattr(arg, "name") and (arg.name is not None):
                return arg.name
            else:
                return str(arg)
        argstrs = tuple(map(str_conv, self.args))

        try:
            binop = self.binops[self.operation]
        except KeyError:
            return f"{self.operation}({','.join(argstrs)})"
        else:
            assert len(self.args) == 2
            return f"({argstrs[0]}{binop}{argstrs[1]})"

    def __repr__(self):
        try:
            binop = self.binops[self.operation]
        except KeyError:
            return f"{self.operation}({','.join(str(arg) for arg in self.args)})"
        else:
            assert len(self.args) == 2
            return f"({repr(self.args[0])}{binop}{repr(self.args[1])})"


class AssuraInterpreter(SkillInterpreter):
    def __init__(self):
        super().__init__()
        self.drcextracts = []

        for name in (
            "drcExtractRules", "drc", "errorLayer", "if", #"switch",
            "extractDevice", "extractRES", "extractCAP", "extractDIODE",
            "extractMOS", "extractBJT",
        ):
            self.register_callback(name, getattr(self, "interpret_"+name))

        for op in (
            "geomAnd", "geomAndNot", "geomAvoiding", "geomBkgnd", "geomButting", "geomButtOnly",
            "geomButtOrCoin", "geomButtOrOver",
            "geomCat", "geomConnect", "geomContact", "geomContactCheck",
            "geomEmpty", "geomEnclose", "geomEncloseRect",
            "geomGetAdjacentEdge", "geomGetAngledEdge", "geomGetBBox", "geomGetCorner", "geomGetCoverage",
            "geomGetEdge", "geomGetHoled", "geomGetLength", "geomGetNet", "geomGetNon45", "geomGetNon90",
            "geomGetRectangle", "geomGetTexted", "geomGetUnTexted", "geomGetVertex", "geomGrow",
            "geomHoles",
            "geomInside", "geomInsidePerShapeArea",
            "geomNodeRelate", "geomNoHoles",
            "geomOr", "geomOutside", "geomOverlap",
            "geomSize", "geomSizeAnd", "geomSizeAndNot", "geomSizeAndProc", "geomStamp", "geomStraddle",
            "geomStretch", "geomStretchCorner",
            "geomTextShape",
            "geomWidth", "geomXor",
        ):
            self.register_callback(op, self.interpret_operation, operation=op)

    def interpret_setq(self, context, args):
        ret = super().interpret_setq(context, args)

        if isinstance(ret, LayerOperation):
            ret.name = args[0]

        return ret

    def interpret_drcExtractRules(self, context, args):
        drcextractcontext = DRCExtractContext(context)
        self.drcextracts.append(drcextractcontext)

        def get_specname(spec):
            assert len(spec) == 1
            for stype, subspec in spec.items():
                if isinstance(subspec, list):
                    layerspecname = "("+"|".join(_util.strip_literal(s) for s in subspec)+")"
                else:
                    assert isinstance(subspec, str)
                    layerspecname = _util.strip_literal(subspec)
                return stype+":"+layerspecname

        layerdefs = args["layerDefs"]
        # Check if layer list is the same for all types
        lnames = None
        for ltype, ldefs in layerdefs.items():
            s = set(ldefs.keys())
            if lnames is None:
                lnames = s
            else:
                assert len(lnames) == len(s) and lnames.issubset(s)

        ltypes = list(layerdefs.keys())
        for layer in lnames:
            layerdef = LayerDef(
                (ltype, get_specname(layerdefs[ltype][layer])) for ltype in ltypes
            )
            drcextractcontext.add_var({layer: layerdef})

        drcextractcontext.add_procedures(args["procedures"])
        self(expr=args["statements"], context=drcextractcontext)

        return "Assura:drcExtractRules"

    def interpret_drc(self, context, args):
        context.rules.append(args)

    def interpret_errorLayer(self, context, args):
        context.rules.append([
            self(expr=args[0], context=context),
            ["errorLayer"], *args[1:],
        ])

    def interpret_operation(self, context, args, *, operation):
        args = [self(expr=arg, context=context) for arg in args]
        return LayerOperation(operation, args)

    def interpret_if(self, context, args):
        cond = self(expr=args["cond"], context=context)
        if isinstance(cond, bool):
            if cond:
                ret = self(expr=args["then"]["statements"], context=context)
            else:
                if "else" in args:
                    ret = self(expr=args["else"]["statements"], context=context)
                else:
                    ret = False
        else:
            args["cond"] = cond
            ret = args

        return ret

    def interpret_switch(self, context, args):
        assert len(args) == 1
        var = _util.strip_literal(args[0])
        return context.get_var(var)

    def interpret_extractDevice(self, context, args):
        assert isinstance(args, dict)
        type_ = args["type"]
        if type_ in context.extracts:
            context.extracts[type_].append(args)
        else:
            context.extracts[type_] = [args]
        return args

    interpret_extractRES = interpret_extractDevice
    interpret_extractCAP = interpret_extractDevice
    interpret_extractDIODE = interpret_extractDevice
    interpret_extractMOS = interpret_extractDevice
    interpret_extractBJT = interpret_extractDevice


#
# Assura function parser support
#
def _switch(elems, **kwargs):
    assert len(elems) == 1
    elem = _util.strip_literal(elems[0])
    return elem


def _layerDefs(elems, **kwargs):
    def parse_type(layerspecs, base, typespec):
        base = _util.strip_literal(base)
        if type(typespec) is list:
            if len(typespec) == 3 and typespec[1] == ":":
                layerspecs.append("{}.{}-{}".format(
                    base, typespec[0], typespec[2]
                ))
            else:
                for v in typespec:
                    parse_type(layerspecs, base, v)
        else:
            if typespec in ("drawing", '"drawing"'):
                layerspecs.append(base)
            else:
                layerspecs.append(base+"."+_util.strip_literal(str(typespec)))


    name = _util.strip_literal(elems[0])
    d = {}
    for elem in elems[1:]:
        assert len(elem) == 3 and elem[1] == "="
        layername, _, expr = elem
        assert len(expr) == 1
        for layerfunc, layerspec in expr.items():
            assert layerfunc in (
                "cellBoundary", "layer", "text", "textFile", "textToPin", "pinText", "pinLayer",
            )
            if layerfunc == "textFile":
                # TODO: Handle textFile properly
                if "_textFile" not in d:
                    d["_textFile"] = [layerspec]
                else:
                    d["_textFile"].append(layerspec)
            else:
                layerspecs = []
                if len(layerspec) == 2 and type(layerspec[1]) is dict:
                    base = str(layerspec[0])
                    layertype = layerspec[1]
                    assert len(layertype) == 1
                    parse_type(layerspecs, base, _util.strip_literal(layertype["type"]))
                else:
                    for l in layerspec:
                        if type(l) is list:
                            if len(l) == 1:
                                layerspecs.append(str(l[0]))
                            elif len(l) == 2:
                                base = str(l[0])
                                layertype = l[1]
                                assert len(layertype) == 1
                                parse_type(layerspecs, base, _util.strip_literal(layertype["type"]))
                            else:
                                raise ValueError(f"type dict expected as second element in {l!r}")
                        else:
                            layerspecs.append(str(l))
                if len(layerspecs) == 1:
                    layerspecs = layerspecs[0]
                d[layername] = {layerfunc: layerspecs}

    return {name: d}


def _drcExtractRules(elems, *, top=True, unknownfuncs=set(), **kwars):
    _known_funcs = {
        "if", "when", "for", "foreach", "evalstring", "sprintf", "let", "prog", "lambda",
        "abs", "exp", "fix", "sqrt",
        "minusp", "plusp", "zerop", # Are these build in ?
        "gate", "antenna", "measure", "calculate", "area", "layerList", "via", "output",
        "cellView", "termOrder",
        "buttOrOver", "drc", "drcAntenna", "errorLayer", "flatErrorLayer", "offGrid", "overlap",
        "keepLayer", "rcxLayer",
        "geomAnd", "geomAndNot", "geomAvoiding", "geomBkgnd", "geomButting", "geomButtOnly",
        "geomButtOrCoin", "geomButtOrOver",
        "geomCat", "geomConnect", "geomContact", "geomContactCheck",
        "geomEmpty", "geomEnclose", "geomEncloseRect",
        "geomGetAdjacentEdge", "geomGetAngledEdge", "geomGetBBox", "geomGetCorner", "geomGetCoverage",
        "geomGetEdge", "geomGetHoled", "geomGetLength", "geomGetNet", "geomGetNon45", "geomGetNon90",
        "geomGetRectangle", "geomGetTexted", "geomGetUnTexted", "geomGetVertex", "geomGrow",
        "geomHoles",
        "geomInside", "geomInsidePerShapeArea",
        "geomNodeRelate", "geomNoHoles",
        "geomOr", "geomOutside", "geomOverlap",
        "geomSize", "geomSizeAnd", "geomSizeAndNot", "geomSizeAndProc", "geomStamp", "geomStraddle",
        "geomStretch", "geomStretchCorner",
        "geomTextShape",
        "geomWidth", "geomXor",
        "generateRectangle",
        "processAntenna", "processCoverage",
        "bulkLayers", "edgeLayers", "withinLayer",
        "attachParameter", "measureParameter", "nameParameter",
        "measureProximity2", "measureSTI",
        "calculateEdges4", "calculateExp", "calculateParameter",
        "extractBJT", "extractCAP", "extractDevice", "extractDIODE", "extractMOS", "extractRES",
        "spiceModel", "targetLayer",
        "saveInterconnect", "saveProperty", "saveRecognition",
        "diffusion", #?
        "label", #?
        "shielded", #?
        "resetCumulative", #?
        "svia", #?
        "step", #?
    }

    _dont_scan = {
        "extractBJT", "extractCAP", "extractDevice", "extractDIODE", "extractMOS", "extractRES",
    }

    def _scan4unknownfuncs(elem):
        if isinstance(elem, dict):
            for funcname, args in elem.items():
                if funcname not in _known_funcs:
                    unknownfuncs.add(funcname)
                if funcname in ("if", "let", "for", "foreach"):
                    for _, args2 in args.items():
                        _scan4unknownfuncs(args2)
                elif funcname not in _dont_scan:
                    _scan4unknownfuncs(args)
        elif isinstance(elem, list):
            for v in elem:
                _scan4unknownfuncs(v)

    begin = 0
    value = {
        "layerDefs": {},
        "procedures": {},
        "statements": [],
    }
    for elem in elems:
        if isinstance(elem, dict):
            assert len(elem) == 1
            for key, body in elem.items():
                if key == "layerDefs":
                    value["layerDefs"].update(body)
                elif key == "procedure":
                    header = body[0]
                    assert type(header) is dict and len(header) == 1
                    for funcname, args in header.items():
                        subvalue = _drcExtractRules(body[1:], top=False, unknownfuncs=unknownfuncs)
                        assert "layerDefs" not in subvalue
                        value["procedures"][funcname] = {
                            "args": args,
                            "body": subvalue["statements"],
                        }
                elif key in ("if", "ivIf", "when"):
                    d = {
                            key:
                            statements if key == "cond" else _drcExtractRules(
                                statements, top=False, unknownfuncs=unknownfuncs
                            )
                         for key, statements in body.items()
                    }
                    assert "procedures" not in d["then"]
                    if "else" in d:
                        assert "procedures" not in d["else"]
                    value["statements"].append({"if": d}) # Convert all to if
                elif key in ("let", "prog"):
                    d = {"vars": body["vars"]}
                    d.update(_drcExtractRules(body["statements"], top=False, unknownfuncs=unknownfuncs))
                    value["statements"].append({"let": d})
                else:
                    if key not in _dont_scan:
                        _scan4unknownfuncs(elem)
                    value["statements"].append(elem)
            begin += 1
        else:
            _scan4unknownfuncs(elem)
            value["statements"].append(elem)
            begin += 1

    if len(value["layerDefs"]) == 0:
        value.pop("layerDefs")

    if len(value["procedures"]) == 0:
        value.pop("procedures")
    else:
        unknownfuncs -= set(value["procedures"].keys())

    if top and len(unknownfuncs) > 0:
        print("Unknown functions in drcExtractRules:")
        for func in unknownfuncs:
            print(f"\t{func}")
        raise(ValueError)

    return value


def _extractDevice(elems, *, type_, **kwargs):
    value = {
        "name": _util.strip_literal(elems[0]),
        "type": type_,
        "layer": elems[1],
    }
    for elem in elems[2:]:
        if isinstance(elem, (dict, list)):
            if isinstance(elem, dict):
                assert(len(elem)) == 1
                key, v = _util.get_first_of(elem.items())
            else:
                key = elem[0]
                v = elem[1:]
            if key in ("spiceModel", "cellView", "targetLayer"):
                assert len(v) == 1
                value[key] = _util.strip_literal(v[0])
            else:
                for v2 in v:
                    value[_util.strip_literal(v2)] = key
        elif elem in ("physical", "flagMalformed"):
            value[elem] = True
        else:
            raise(ValueError(f"{elems[0]}: {elem}"))

    return value


_value4function_table = {
    "switch": _switch,
    "avSwitch": _switch,
    "ivIf": _skill_if, # Treat as if alias
    "drcExtractRules": _drcExtractRules,
    "layerDefs": _layerDefs,
    "extractRES": (_extractDevice, {"type_": "resistors"}),
    "extractCAP": (_extractDevice, {"type_": "capacitors"}),
    "extractDIODE": (_extractDevice, {"type_": "diodes"}),
    "extractMOS": (_extractDevice, {"type_": "mosfets"}),
    "extractBJT": (_extractDevice, {"type_": "bipolars"}),
    "extractDevice": (_extractDevice, {"type_": "devices"}),
    #TODO: avCompareRules
}


#
# Grammar
#
class AssuraFile(SkillFile):
    def grammar_elem_init(self, sessiondata):
        super().grammar_elem_init(sessiondata)
        self.ast = {"AssuraFile": self.ast["SkillFile"]}
        self.value = {"AssuraFile": self.value["SkillFile"]}

    @classmethod
    def parse_string(cls, text):
        return super().parse_string(text, value4funcs=_value4function_table)


class AssuraDRC(dict):
    @staticmethod
    def _cond2str(expr):
        if isinstance(expr, list):
            return "("+" ".join(AssuraDRC._cond2str(item) for item in expr)+")"
        elif isinstance(expr, dict):
            assert len(expr) == 1
            for key, args in expr.items():
                return key+AssuraDRC._cond2str(args)
        else:
            return str(expr)

    def extract_checks(self, value, *, condstr=""):
        for expr in value:
            if isinstance(expr, dict):
                for key, value in expr.items():
                    if key == "if":
                        condstr2 = self._cond2str(value["cond"])
                        if len(condstr) > 0:
                            condstr2 = condstr+"&&"+condstr2
                        self.extract_checks(
                            value=value["then"]["statements"],
                            condstr=condstr2,
                        )
                        if "else" in value:
                            condstr2 = "!"+self._cond2str(value["cond"])
                            if len(condstr) > 0:
                                condstr2 = condstr+"&&"+condstr2
                            self.extract_checks(
                                value=value["else"]["statements"],
                                condstr=condstr2,
                            )
                    elif key in ("drc", "errorLayer", "offGrid"):
                        self.add_check(condstr, key, value)

    def add_check(self, condstr, checktype, check):
        try:
            conddata = self[condstr]
        except KeyError:
            self[condstr] = conddata = {}

        try:
            conddata[checktype].append(check)
        except KeyError:
            conddata[checktype] = [check]

    def print_checks(self):
        keys = list(self.keys())
        keys.sort()

        for key in keys:
            print("{}:".format("Unconditioned" if key == "" else key))
            for checktype, checks in self[key].items():
                print(f"  {checktype}:")
                for check in checks:
                    print(f"    {check}")

    def get_sigs(self):
        sigs = {}
        for _, checktypes in self.items():
            for checktype, checks in checktypes.items():
                if checktype not in ("drc", "errorLayer", "offGrid"):
                    continue
                checksigs = {tuple(type(expr) for expr in check) for check in checks}
                if checktype in sigs:
                    sigs[checktype].update(checksigs)
                else:
                    sigs[checktype] = checksigs

        return sigs

