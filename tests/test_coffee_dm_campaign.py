"""Offline campaign contract tests, no GitHub/R2/solver/provider consumption."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import test_coffee_domain
from arena.common import ArenaError, digest, write_json
from arena.coffee_domain import build_case
from arena.coffee_native_dm import prepare
from arena import coffee_dm_campaign as campaign


class CoffeeDMCampaignTests(TestCase):
    setUp = test_coffee_domain.CoffeeDomainTests.setUp

    def identity_env(self):
        return {"GITHUB_EVENT_NAME":"push",
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_REPOSITORY":campaign.REPO,
                "GITHUB_RUN_ATTEMPT":"1", "GITHUB_RUN_ID":"987"}

    def fixtures(self):
        case=build_case(self.public,test_coffee_domain.ASSUMPTIONS,environment={})
        vars={
            "SOURCE_RUN_ID":123, "SOURCE_SHA":"a"*40,
            "SOURCE_PACKAGE_SHA256":case["source_package_sha256"],
            "PUBLIC_SHA256":case["public_sha256"],
            "CASE_SHA256":digest(case),
            "SELECTION":case["selection"],
            "ARTIFACT_ID":77,
        }
        stack=ExitStack()
        for name,value in vars.items():
            stack.enter_context(patch.object(campaign,name,value))
        return stack,case

    def test_first_attempt_read_only_and_no_provider_secret(self):
        self.assertEqual(campaign.identity(self.identity_env()),987)
        for key,value in (("GITHUB_REF","refs/heads/dev"),
                          ("GITHUB_RUN_ATTEMPT","2"),
                          ("GITHUB_REPOSITORY","other/repo"),
                          ("CT03_R2_ACCESS_KEY_ID","private"),
                          ("CLOUDFLARE_API_TOKEN","provider")):
            env=self.identity_env();env[key]=value
            with self.subTest(key=key),self.assertRaises(ArenaError):
                campaign.identity(env)

    def test_public_zip_exact_hash_and_only_two_members(self):
        import io
        import zipfile
        payloads={p.name:p.read_bytes() for p in self.public.iterdir()}
        def create(extra=None):
            dest=io.BytesIO()
            with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED) as f:
                for name,blob in payloads.items():
                    f.writestr(name,blob)
                if extra:
                    f.writestr(extra,"secret")
            return dest.getvalue()
        with self.fixtures()[0]:
            raw=create()
            with patch.object(campaign,"ARCHIVE_SHA256",hashlib.sha256(raw).hexdigest()):
                self.assertEqual(set(campaign.validate_public_zip(raw)),set(payloads))
                with self.assertRaisesRegex(ArenaError,"SOURCE_ARTIFACT_ZIP_SHA256_MISMATCH"):
                    campaign.validate_public_zip(raw+b"changed")
            extra=create("private/linkage.json")
            with patch.object(campaign,"ARCHIVE_SHA256",hashlib.sha256(extra).hexdigest()):
                with self.assertRaisesRegex(ArenaError,"UNEXPECTED_PUBLIC_ARTIFACT_MEMBERS"):
                    campaign.validate_public_zip(extra)

    def test_twelve_real_fixture_natives_static_audited_but_not_simulated(self):
        stack,case=self.fixtures()
        with stack:
            source={"status":"EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED",
                    "source_artifact_id":77, "case_sha256":digest(case)}
            write_json(self.root/"attestation.json",source,exclusive=True)
            result=prepare(self.public,test_coffee_domain.ASSUMPTIONS,
                           self.root/"native",verify_original=True,environment={})
            self.assertEqual(result["arms"],{"D":6,"M":6})
            audited=campaign.audit(self.root)
            self.assertEqual(audited["status"],
                             "TWELVE_NATIVE_CANDIDATES_STATIC_AUDITED_NOT_SIMULATED")
            self.assertEqual(audited["solver"]["new_omc_attempts"],0)
            self.assertFalse(audited["ledger_atms_feedback_consumed"])
            self.assertFalse(audited["reserved_truth_opened"])
            for arm in ("D","M"):
                self.assertEqual(len(audited["arms"][arm]["candidates"]),6)
                self.assertEqual({x["status"] for x in
                                  audited["arms"][arm]["candidates"]},
                                 {"STATIC_STRUCTURE_CHECKED_NOT_COMPILED"})
            self.assertTrue(any(c["facts"]["catalog_transit_response_time_hours"]==1.6
                                for c in audited["arms"]["M"]["candidates"]))
            files=list((self.root/"native/D").glob("*.mo"))
            file=files[0]
            file.write_text(file.read_text()+"\n// TAMPER",encoding="utf-8")
            with self.assertRaisesRegex(ArenaError,"NATIVE_FILE_BYTES_MISMATCH"):
                campaign.audit(self.root,out=self.root/"audit-tampered.json")

    def test_provenance_mismatch_blocks_native_audit(self):
        stack,case=self.fixtures()
        with stack:
            write_json(self.root/"attestation.json",{
                "status":"EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED",
                "source_artifact_id":77, "case_sha256":"sha256:"+"f"*64},
                exclusive=True)
            prepare(self.public,test_coffee_domain.ASSUMPTIONS,
                    self.root/"native",verify_original=False,environment={})
            with self.assertRaisesRegex(ArenaError,"BAD_ADMISSION_RECEIPT"):
                campaign.audit(self.root)
