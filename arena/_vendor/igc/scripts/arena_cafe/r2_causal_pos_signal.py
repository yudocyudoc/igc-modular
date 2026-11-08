"""RF-02T: causal, right-sided POS event-rate approximation for D-B.

This is an explicit ENGINEERING stimulus policy, not a measured instantaneous
rate and not scientific identification. Each observed order at t_i contributes
exactly one unit uniformly on [t_i, t_i + width); never before t_i.
Any support beyond the observation cutoff is reported as DEFERRED MASS, not
deleted, placed before the event, or reconstructed from delivered orders.

Pure-Python signal arithmetic, no DES, OpenModelica, provider, selection, G2/G3.
Modelica text generation is an explicitly separate, opt-in engineering function
for independently documented nominal parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest, ArenaContractError
from scripts.arena_cafe.native_handoff import need, validate_a1_visible
from scripts.arena_cafe import r2_observational_contracts as r2
from scripts.arena_d_v01 import modelica as native_d_modelica

SCHEMA="igc-arena-d-pos-causal-stimulus/0.1"
RENDER_SCHEMA="igc-arena-d-pos-modelica-engineering/0.1"
POLICY="CAUSAL_RIGHT_RECTANGULAR_EVENT_KERNEL/0.1"
CANONICAL_WIDTH=Fraction(1,2)  # 0.5 min, declared before any new score
SENSITIVITY_WIDTHS=(Fraction(1,4), CANONICAL_WIDTH, Fraction(1,1))
LEGACY_INPUT="  inputRate = if time < pulseDuration then pulseRate else 0;"
LEGACY_RATE="  parameter Real pulseRate = 1;"
LEGACY_DURATION="  parameter Real pulseDuration = 1;"


def qstr(n):
    return str(n)


def _fraction(value):
    try:
        answer=Fraction(value)
    except (ValueError,TypeError,ZeroDivisionError) as exc:
        raise ArenaContractError("R2T_INVALID_RATIONAL") from exc
    return answer


def _signal(times,cutoff,width):
    """Exact half-open piecewise rate and integration with fraction arithmetic."""
    cutoff=_fraction(cutoff)
    width=_fraction(width)
    need(cutoff>0 and width in SENSITIVITY_WIDTHS, "R2T_NONDECLARED_KERNEL_WIDTH")
    times=[_fraction(t) for t in times]
    need(all(0<=t<cutoff for t in times), "R2T_FUTURE_OR_NEGATIVE_EVENT")
    need(times==sorted(times), "R2T_NONMONOTONE_EVENTS")
    changes=defaultdict(Fraction)
    changes[Fraction(0)]+=0
    changes[cutoff]+=0
    for t in times:
        changes[t]+=1/width
        changes[t+width]-=1/width
    end=max([cutoff]+[t+width for t in times])
    changes[end]+=0
    points=sorted(changes)
    rate=Fraction(0)
    segments=[]
    for i,t in enumerate(points[:-1]):
        rate+=changes[t]
        next_t=points[i+1]
        need(next_t>t and rate>=0,"R2T_RATE_ORDER_OR_NEGATIVE")
        segments.append({"start_minutes_exact":qstr(t),
                         "end_minutes_exact":qstr(next_t),
                         "rate_orders_per_minute_exact":qstr(rate),
                         "mass_orders_exact":qstr(rate*(next_t-t))})
    need(rate+changes[points[-1]]==0,
         "R2T_STIMULUS_DOES_NOT_CLOSE")
    before=sum((Fraction(s["mass_orders_exact"]) for s in segments
                if Fraction(s["end_minutes_exact"])<=cutoff),Fraction(0))
    after=sum((Fraction(s["mass_orders_exact"]) for s in segments
               if Fraction(s["start_minutes_exact"])>=cutoff),Fraction(0))
    need(before+after==len(times),"R2T_MASS_LOST")
    need(all(Fraction(s["rate_orders_per_minute_exact"])>=0 for s in segments),
         "R2T_NEGATIVE_RATE")
    return {
        "policy":POLICY,
        "width_minutes_exact":qstr(width),
        "event_times_minutes_exact":[qstr(t) for t in times],
        "cutoff_minutes_exact":qstr(cutoff),
        "support_end_minutes_exact":qstr(end),
        "segments":segments,
        "events_count":len(times),
        "total_event_mass_orders_exact":qstr(Fraction(len(times))),
        "mass_before_cutoff_orders_exact":qstr(before),
        "mass_deferred_after_cutoff_orders_exact":qstr(after),
        "tail_not_truncated_or_moved_before_event":True,
        "rate_not_instrument_measured":True,
        "no_lookahead_in_mathematical_kernel":True,
        "causal_event_support":"[event_t,event_t+width)",
        "number_of_temporal_approximations":1,
        "method":"EXTERNAL_ARENA_ENGINEERING_SIGNAL_NOT_D_NATIVE_INFERENCE",
        "event_rate_signal_sha256":digest({
            "policy":POLICY, "width":qstr(width),"events":[qstr(t) for t in times],
            "cutoff":qstr(cutoff),
        }),
    }


def event_rate_at(times,width,t):
    """Exact analytic rate; only for negative tests/conformance, not sampling."""
    times=[_fraction(x) for x in times]
    width=_fraction(width)
    t=_fraction(t)
    need(width>0, "R2T_BAD_RATE_WIDTH")
    return sum((Fraction(1,1)/width
                for e in times if e<=t<e+width),Fraction(0))


def event_mass_until(times,width,t):
    """Exact causal cumulative input including partially injected last events."""
    times=[_fraction(x) for x in times]
    width=_fraction(width)
    t=_fraction(t)
    need(width>0,"R2T_BAD_INTEGRAL_WIDTH")
    return sum((max(Fraction(0),min(t-e,width))/width
                for e in times),Fraction(0))


def from_visible(visible,condition,width=CANONICAL_WIDTH):
    validate_a1_visible(visible,condition)
    events=visible["construction"]["pos_arrival_events"]
    cutoff=Fraction(visible["observability"]["cutoff_minutes_exact"])
    times=[Fraction(item["t_minutes_exact"]) for item in events]
    s=_signal(times,cutoff,width)
    return {
        "schema":SCHEMA,
        "condition_id":condition,
        "public_input_sha256":digest(visible),
        "public_source_snapshot_hash":visible["source_snapshot_hash"],
        "event_source_field":"construction.pos_arrival_events",
        "events_hash":digest(events),
        "observed_input_events_not_deliveries":True,
        "known_arrival_events_not_known_instantaneous_rate":True,
        "policy_role":"ARENA_ENGINEERING_APPROXIMATION_NOT_MEASURED_RATE",
        "not_original_D_pulse":True,
        "scientific_policy_approval":"NOT_GRANTED",
        "selection_after_G3":"FORBIDDEN",
        "modelica_time_unit":"minute",
        "modelica_rate_unit":"orders/minute",
        "signal":s,
        "G2":"NOT_RUN","G3":"NOT_RUN",
        "provider_calls":0,"solver_invocations":0,
    }


def _real(q):
    """Modelica Real expression explicitly divides Real literals for fractions."""
    q=_fraction(q)
    if q.denominator==1:
        return str(q.numerator)+".0"
    return "("+str(q.numerator)+".0/"+str(q.denominator)+".0)"


def modelica_event_expression(signal):
    """Use exact event boundaries; rate is one order per width, sum overlaps."""
    need(signal["policy"]==POLICY,"R2T_NOT_OUR_CAUSAL_POLICY")
    width=_fraction(signal["width_minutes_exact"])
    times=[_fraction(x) for x in signal["event_times_minutes_exact"]]
    need(width in SENSITIVITY_WIDTHS and times==sorted(times),
         "R2T_NONDECLARED_RENDER")
    rate=_real(1/width)
    if not times:
        return "0.0"
    pieces=[]
    for t in times:
        pieces.append("(if time >= "+_real(t)+" and time < "+
                      _real(t+width)+" then "+rate+" else 0.0)")
    return " + ".join(pieces)


def render_six_with_declared_nominals(visible,condition,parameters, *,
                                       width=CANONICAL_WIDTH,budget=None):
    """Opt-in six Modelica TEXT variants; NEVER execute or rank them.

    The D original Modelica renderer supplies the exact conservation/equation
    skeleton. Only the input function is replaced. Dummy pulse declarations are
    then removed as unused; the genuine D capacity/loss equations are unchanged.
    Rendering is blocked absent 3 independently attributed values.
    """
    original=r2.d_pos_contract(
        visible,condition,
        resources=(budget or {"max_stocks":3,"allow_loss":True,
                             "max_candidates":6,"max_simulations":0}),
        nominal=parameters,
    )
    need(original["candidate_count"]>0 and
         original["nominal_parameters_provenance"] is not None,
         "R2T_NOMINAL_VALUES_REQUIRED")
    s=from_visible(visible,condition,width)
    expressions=modelica_event_expression(s["signal"])
    numeric={name:original["nominal_parameters_provenance"][name]["value"]
             for name in r2.D_PARAMETERS}
    rows=[]
    for candidate in original["candidates"]:
        shell={**candidate,"nominal_parameters":numeric}
        stock_source=native_d_modelica(
            shell,{"kind":"pulse","rate":1.0,"duration":1.0})
        need(stock_source.count(LEGACY_INPUT)==1 and
             stock_source.count(LEGACY_RATE)==1 and
             stock_source.count(LEGACY_DURATION)==1,
             "R2T_NATIVE_RENDERER_SOURCE_DRIFT")
        transformed=stock_source.replace(LEGACY_INPUT,
                                        "  inputRate = "+expressions+";")
        transformed=transformed.replace(LEGACY_RATE+"\n","")
        transformed=transformed.replace(LEGACY_DURATION+"\n","")
        # Guard derivative equations are literally untouched, not rederived.
        old_eq=[line.strip() for line in stock_source.splitlines()
                if line.strip().startswith(("der(","f","lossRate =")) and
                (" = " in line)]
        new_eq=[line.strip() for line in transformed.splitlines()
                if line.strip().startswith(("der(","f","lossRate =")) and
                (" = " in line)]
        need(old_eq==new_eq and len(old_eq)>=len(
             candidate["structure"]["stocks"])*2+2,
             "R2T_D_NATIVE_EQUATIONS_CHANGED")
        need("pulseRate" not in transformed and
             "pulseDuration" not in transformed,
             "R2T_FAKE_PULSE_DECLARATIONS")
        name="DStockFlow_"+candidate["structure_hash"][7:19]
        rows.append({
            "candidate_id":candidate["id"],
            "structure_hash":candidate["structure_hash"],
            "model_name":name,
            "modelica":transformed,
            "modelica_sha256":"sha256:"+hashlib.sha256(transformed.encode()).hexdigest(),
            "source_renderer":"scripts.arena_d_v01.modelica",
            "source_renderer_reused":True,
            "modification":"EXTERNAL_STIMULUS_ONLY_AND_REMOVE_UNUSED_PULSE_DECLARATIONS",
            "all_native_balance_and_bound_equations_unchanged":True,
            "input_signal_sha256":s["signal"]["event_rate_signal_sha256"],
            "parameters_source":"EXTERNALLY_DECLARED_WITH_PROVENANCE_NOT_D_INFERENCE",
            "G0":"ENGINEERING_RENDER_EMITTED",
            "G1":"SOURCE_GRAMMAR_AND_LINTER_ACCEPTED",
            "G2":"NOT_RUN","G3":"NOT_RUN",
            "independent_method_selection":False,
        })
    return {
        "schema":RENDER_SCHEMA,
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "condition_id":condition,
        "policy":s["signal"],
        "engine":"D_OBSERVED_POS_EXTENSION/0.1",
        "original_d_source_protected":True,
        "nominal_parameters_provenance":original["nominal_parameters_provenance"],
        "candidate_count":len(rows),
        "candidates":rows,
        "selection_owner":"NONE",
        "solver_invocations":0,"provider_calls":0,
        "scientific_adequacy":"NOT_ESTABLISHED",
        "G2":"NOT_RUN","G3":"NOT_RUN","G4":"NOT_RUN","G5":"NOT_RUN",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--condition",required=True,choices=("O0","O1"))
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--width-minutes",default="1/2")
    p.add_argument("--nominal-provenance",type=Path)
    p.add_argument("--render-engineering-modelica",action="store_true")
    args=p.parse_args()
    need(not args.out.exists(),"R2T_REFUSE_OVERWRITE")
    view=json.loads(args.input.read_text())
    if args.render_engineering_modelica:
        need(args.nominal_provenance is not None,
             "R2T_REQUIRES_DECLARED_NOMINAL_PROVENANCE")
        params=json.loads(args.nominal_provenance.read_text())
        report=render_six_with_declared_nominals(
            view,args.condition,params,width=_fraction(args.width_minutes))
        out=args.out
        out.mkdir(parents=True,exist_ok=False)
        data=dict(report)
        data["candidates"]=[
            {k:v for k,v in row.items() if k!="modelica"}
            for row in report["candidates"]]
        for row in report["candidates"]:
            path=out/(row["model_name"]+".mo")
            path.write_text(row["modelica"],encoding="utf-8",newline="\n")
        (out/"manifest.json").write_bytes(canonical(data)+bytes([10]))
        print(json.dumps({"state":"ENGINEERING_TEXT_ONLY_NOT_G2",
                          "models":len(report["candidates"])}))
    else:
        need(args.nominal_provenance is None,
             "R2T_NOMINALS_WITHOUT_OPT_IN_RENDER_NOT_USED")
        doc=from_visible(view,args.condition,_fraction(args.width_minutes))
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_bytes(canonical(doc)+bytes([10]))
        print(json.dumps({"state":"CAUSAL_SIGNAL_PROPOSED_NO_G2",
                          "before_cutoff":doc["signal"]["mass_before_cutoff_orders_exact"],
                          "deferred":doc["signal"]["mass_deferred_after_cutoff_orders_exact"]}))


if __name__=="__main__":
    main()
