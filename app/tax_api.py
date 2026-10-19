"""HTTP contract for tax choices: one place for the request and response shapes a future frontend consumes."""

import re
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from . import taxes


class TaxSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pph: str = Field(min_length=1, max_length=20)
    ppn: StrictBool
    recipient_has_npwp: StrictBool
    faktur_number: str | None = Field(default=None, max_length=40)
    ppn_adjustment: Literal['NONE', 'ADD_ON'] = 'NONE'
    ppn_adjustment_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def known_and_complete(self):
        # Since schema v2 the faktur number is read from the document, so PPN no longer requires a typed one.
        # A typed number is still only allowed with PPN, and must be 13 to 17 digits.
        digits = re.sub(r'[.\-\s]', '', self.faktur_number or '')
        if self.pph not in taxes.PPH or (digits and not self.ppn) or (digits and not re.fullmatch(r'\d{13,17}', digits)):
            raise ValueError('Pilihan pajak tidak valid.')
        if self.ppn_adjustment == 'ADD_ON' and (not self.ppn or len((self.ppn_adjustment_reason or '').strip()) < 5):
            raise ValueError('Tambahan PPN memerlukan pilihan PPN dan alasan minimal 5 karakter.')
        return self


class TaxExample(BaseModel):
    gross: str
    withheld: str
    net: str


class TaxPreset(BaseModel):
    id: str
    label: str
    pph: str
    ppn: bool


class TaxSource(BaseModel):
    label: str
    url: str


class TaxOption(BaseModel):
    id: str
    label: str
    short: str
    rate_text: str
    basis: str
    ref_ids: list[str]
    source: TaxSource | None
    example: TaxExample


class PpnRule(BaseModel):
    label: str
    basis: str
    ref_ids: list[str]
    source: TaxSource


class TaxRules(BaseModel):
    rules_version: str
    verified_on: str
    status_note: str
    presets: list[TaxPreset]
    pph: list[TaxOption]
    ppn: PpnRule
    rounding_source: TaxSource


def tax_router(actor):
    router = APIRouter(prefix='/api/v1')

    @router.get('/tax/rules', response_model=TaxRules)
    def rules(user=Depends(actor)):
        return taxes.options()

    return router
