"""BF-02: freeze public-only versioned instructions and parent-specific feedback.

The original engine is not patched and none of its system instructions are
secretly replaced. This prepares packets, NOT approval for a paid request.
"""
from hashlib import sha256
import json
from .capabilities import CAPABILITY_VERSION,PROFILE_ID,capability_report,canonical,native_hash
from .validation import diagnose

PROFILE = """BUFFALO-ADJUST-V1 / public construction task

Retain the original Buffalo quantitative Engine.generate and its SDK schema.
The mandatory graphicalFunction field DOES NOT mandate a curve. Use
graphicalFunction: {points: []} for stocks, scalar parameters and flows not
capable of graphical lookup under the selected backend. Only put points on
supported auxiliaries when the equation is the real lookup input, with declared
units, interpolation and extrapolation; never use the variable itself as its
input. Do not put time pulse points on every variable.

The exogenous input is exactly 1.7 items/hour from t=0 inclusive to t=2
exclusive, and zero outside: 3.4 items total in continuous time. Do not
approximate it by a ramp or claim that an Euler-grid match is exact. The
original language allows safe division //: x // 0 returns 0, otherwise x/y.
A public exact pulse can use Z(x) = MAX(0,x) // MAX(0,x), expanded inline,
with Pulse_rate * (1 - Z(Start_time - TIME)) * Z(End_time - TIME).
Here Z is mathematical shorthand, not a declared new function. Use only
original operators and named public parameters. Do not infer a structure or
repair a native parent from this neutral input-expression example.
The pinned Modelica translator preserves this // guard. XMILE/PySD parity
is not proven: the original XMILE exporter changes // to ordinary /.
Initial material stocks and cumulative delivery are zero. Horizon 0-8 hours,
Euler step 0.125. Only observations at t=0,1,2,4 are available.

State every structural assumption and its limitations. Do not assert that
numerical calibration or simulation was executed without an execution record.
Do not impose a stage count, single stock, parameter value, other arms' models,
hidden truth, future observations, or a repaired parent equation.
Do not override the upstream system instruction forbidding conditionals.
"""

def freeze_profile():
    capabilities=capability_report()
    return {"schema": "buffalo-adjust-v1/profile/1",
            "id":PROFILE_ID,
            "text":PROFILE,
            "utf8_sha256":"sha256:"+sha256(PROFILE.encode("utf-8")).hexdigest(),
            "backend_capabilities":capabilities,
            "original_system_instruction_modified":False,
            "no_hidden_truth":True,"provider_posts":0,"omc_attempts":0}


def own_feedback(parent, receipt, public_construction, profile):
    """Diagnostic-only packet; no human substitute model and no private field."""
    if profile.get("id") != PROFILE_ID or profile.get("utf8_sha256") != freeze_profile()["utf8_sha256"]:
        raise ValueError("PROFILE_NOT_FROZEN")
    if (receipt.get("model_returned") is not True or
        receipt.get("provider_calls") != 1 or
        receipt.get("round_kind") != "initial" or
        receipt.get("status") != "ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED"):
        raise ValueError("PARENT_MUST_BE_ORIGINAL_LIVE_NATIVE")
    if (receipt.get("source_snapshot_hash")!=public_construction.get("source_snapshot_hash")
        or receipt.get("world_public_id")!=public_construction.get("world_public_id")):
        raise ValueError("PARENT_PUBLIC_IDENTITY_MISMATCH")
    # The parent is immutable; report diagnostics, not a fixed model.
    report=diagnose(parent)
    return {"schema":"buffalo-adjust-v1/own-feedback/1",
            "profile_id":PROFILE_ID,"profile_sha256":profile["utf8_sha256"],
            "parent_native_sha256":native_hash(parent),
            "parent_receipt_result_sha256":receipt.get("result_sha256"),
            "source_snapshot_hash":public_construction.get("source_snapshot_hash"),
            "world_public_id":public_construction.get("world_public_id"),
            "public_construction":public_construction,
            "own_semantic_diagnostics":report,
            "modelica_pulse_compatibility":capability_report()["physical_compatibility"],
            "xmile_pysd_safe_division_parity":"UNPROVEN",
            "not_physical_measurement":True,
            "not_a_repaired_native":True,
            "no_hidden_or_rival_inputs":True,
            "provider_posts":0,"omc_attempts":0}
