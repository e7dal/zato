# -*- coding: utf-8 -*-

"""
Copyright (C) 2017, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# Django
from django import forms

# Zato
from zato.common import CACHE
from zato.admin.web.forms import add_select

class CreateForm(forms.Form):
    id = forms.CharField(widget=forms.HiddenInput())
    name = forms.CharField(widget=forms.TextInput(attrs={'class':'required', 'style':'width:100%'}))
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'checked':'checked'}))
    is_default = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'checked':'checked'}))
    is_debug = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    servers = forms.CharField(widget=forms.Textarea(attrs={'style':'width:100%; height:80px'}))
    extra = forms.CharField(widget=forms.Textarea(attrs={'style':'width:100%%; height:80px'}))

class EditForm(CreateForm):
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    is_default = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    is_debug = forms.BooleanField(required=False, widget=forms.CheckboxInput())