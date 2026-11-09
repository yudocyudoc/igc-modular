"""BF-01: measured capabilities and a fail-closed public input contract.

The exact rectangular pulse is discontinuous. Existing Buffalo system
instructions prohibit IF/THEN/ELSE, and the unchanged Modelica translator
only compiles MIN/MAX/ABS functions. A piecewise-linear lookup is NOT exact.
"""
import copy
from hashlib import sha256
import json
import math

CAPABILITY_VERSION = "buffalo-adjust-v1/bf01"
PROFILE_ID = "buffalo-adjust-v1"
PULSE = {"rate":1.7, "start":0.0,"end":2.0,"mass":3.4}
TRANSLATOR_FUNCS = ["MIN","MAX","ABS"]
BLOCKER = "INPUT_CAPABILITY_GAP"


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()


def native_hash(value):
    return "sha256:"+sha256(canonical(value)).hexdigest()


def exact_public_pulse(time):
    return 1.7 if 0 <= time < 2 else 0.0


def validate_pulse():
    assert exact_public_pulse(-1e-9)==0
    assert exact_public_pulse(0)==1.7
    assert exact_public_pulse(2-1e-9)==1.7
    assert exact_public_pulse(2)==0
    assert exact_public_pulse(2+1e-9)==0
    assert exact_public_pulse(8)==0
    assert abs(1.7*(2-0)-3.4)<1e-12
    return {"schema":CAPABILITY_VERSION,"rate_left_of_t2":1.7,
            "rate_at_t2":0,"analytic_mass":3.4,
            "input_support":"EXACT_MATHEMATICAL_DEFINITION_NOT_BACKEND_EXECUTION",
            "solver_grid_alone_is_not_equivalence":True}


def normalize_units_only(document):
    """One-to-one representational view, never rewrite equations or points."""
    original=copy.deepcopy(document)
    view=copy.deepcopy(document)
    changes=[]
    spec=view["model"]["specs"]
    if spec.get("timeUnits")=="hours":
        spec["timeUnits"]="hour"
        changes.append({"path":"model.specs.timeUnits","from":"hours",
                        "to":"hour","factor":1})
    for idx,v in enumerate(view["model"]["variables"]):
        if v.get("units")=="hours":
            v["units"]="hour"
            changes.append({"path":f"model.variables[{idx}].units",
                            "from":"hours","to":"hour","factor":1})
    if not changes and spec.get("timeUnits") not in ("hour",):
        raise ValueError("UNSUPPORTED_TIME_UNIT")
    # Verify the transformed view differs ONLY at named paths.
    roundtrip=copy.deepcopy(view)
    for t in changes:
        if t["path"]=="model.specs.timeUnits":
            roundtrip["model"]["specs"]["timeUnits"]=t["from"]
        else:
            index=int(t["path"].split("[")[1].split("]")[0])
            roundtrip["model"]["variables"][index]["units"]=t["from"]
    if roundtrip != original:
        raise AssertionError("Unit normalization modified non-unit fields.")
    return {"schema":CAPABILITY_VERSION,
            "original_sha256":native_hash(original),
            "view_sha256":native_hash(view),
            "transformations":changes,
            "source_modified":False,
            "scale_factor":1},view


def capability_report():
    pulse=validate_pulse()
    return {"schema":CAPABILITY_VERSION,
            "model":"@cf/zai-org/glm-5.3-flash",
            "adapter":"igc-b-ev01-workers-rest/0.1",
            "max_completion_tokens":16000,"reasoning_effort":"low",
            "original_system_prohibits_conditionals":True,
            "original_translator_functions":TRANSLATOR_FUNCS,
            "lookups":"LINEAR_INTERPOLATION_CLAMPED_ENDPOINTS_AUXILIARIES_ONLY",
            "exact_public_input":pulse,
            "physical_compatibility":BLOCKER,
            "reason":"An exact [0,2) rectangular pulse has a jump; existing equation "
                     "functions are continuous at t=2 and IF is prohibited by "
                     "the original system instruction and unsupported in the "
                     "unchanged translator. An Euler-grid coincidence does not "
                     "prove continuous-time equivalence.",
            "next_step":"Version an exact input binding or an explicitly derived "
                        "translator/system contract before enabling BF-03.",
            "provider_posts":0,"omc_attempts":0}
