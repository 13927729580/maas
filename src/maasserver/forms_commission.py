# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Commission form."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = [
    "CommissionForm",
]

from django import forms
from django.core.exceptions import ValidationError
from maasserver.enum import POWER_STATE
from maasserver.node_action import compile_node_actions


class CommissionForm(forms.Form):
    """Commission form."""

    enable_ssh = forms.BooleanField(required=False, initial=False)
    block_poweroff = forms.BooleanField(required=False, initial=False)
    skip_networking = forms.BooleanField(required=False, initial=False)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop("instance")
        self.user = kwargs.pop("user")
        super(CommissionForm, self).__init__(*args, **kwargs)

    def _get_node_action(self):
        actions = compile_node_actions(self.instance, self.user)
        return actions.get("commission")

    def clean(self):
        cleaned_data = super(CommissionForm, self).clean()
        action = self._get_node_action()
        if action is None:
            raise ValidationError(
                "Commission is not available because of the current state "
                "of the node.")
        if self.instance.power_state == POWER_STATE.ON:
            raise ValidationError(
                "Commission is not available because of the node is currently "
                "powered on.")
        return cleaned_data

    def save(self):
        enable_ssh = self.cleaned_data.get("enable_ssh", False)
        block_poweroff = self.cleaned_data.get("block_poweroff", False)
        skip_networking = self.cleaned_data.get("skip_networking", False)
        self.instance.start_commissioning(
            self.user, enable_ssh=enable_ssh, block_poweroff=block_poweroff,
            skip_networking=skip_networking)
        return self.instance