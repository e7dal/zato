# -*- coding: utf-8 -*-

"""
Copyright (C) 2018, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import logging
from traceback import format_exc

# Django
from django.http import HttpResponse, HttpResponseServerError

# Zato
from zato.admin.web import from_utc_to_user
from zato.admin.web.forms.pubsub.topic import CreateForm, EditForm
from zato.admin.web.views import CreateEdit, Delete as _Delete, django_url_reverse, Index as _Index, slugify
from zato.admin.web.views.pubsub import get_client_html, get_endpoint_html
from zato.common.odb.model import PubSubEndpoint, PubSubMessage, PubSubTopic

# ################################################################################################################################

logger = logging.getLogger(__name__)

# ################################################################################################################################

class Index(_Index):
    method_allowed = 'GET'
    url_name = 'pubsub-topic'
    template = 'zato/pubsub/topic.html'
    service_name = 'zato.pubsub.topic.get-list'
    output_class = PubSubTopic
    paginate = True

    class SimpleIO(_Index.SimpleIO):
        input_required = ('cluster_id',)
        output_required = ('id', 'name', 'is_active', 'is_internal', 'has_gd', 'is_api_sub_allowed', 'max_depth_gd',
            'max_depth_non_gd', 'current_depth_gd', 'current_depth_non_gd', 'depth_check_freq', 'hook_service_id',
            'pub_buffer_size_gd', 'pub_buffer_size_non_gd', 'deliv_task_sync_interv_gd', 'deliv_task_sync_interv_non_gd')
        output_optional = ('last_pub_time',)
        output_repeated = True

    def on_before_append_item(self, item):
        if item.last_pub_time:
            item.last_pub_time = from_utc_to_user(item.last_pub_time+'+00:00', self.req.zato.user_profile)
        return item

    def handle(self):
        return {
            'create_form': CreateForm(self.req),
            'edit_form': EditForm(self.req, prefix='edit'),
        }

# ################################################################################################################################

class _CreateEdit(CreateEdit):
    method_allowed = 'POST'

    class SimpleIO(CreateEdit.SimpleIO):
        input_required = ('name', 'is_active', 'is_internal', 'has_gd', 'is_api_sub_allowed', 'max_depth_gd',
            'max_depth_non_gd', 'depth_check_freq', 'pub_buffer_size_gd', 'pub_buffer_size_non_gd',
            'deliv_task_sync_interv_gd', 'deliv_task_sync_interv_non_gd')
        input_optional = ('hook_service_id',)
        output_required = ('id', 'name', 'has_gd')

    def post_process_return_data(self, return_data):

        return_data['publishers_link'] = '<a href="{}">{}</a>'.format(
            django_url_reverse('pubsub-topic-publishers',
                kwargs={'cluster_id':self.req.zato.cluster_id,
                        'topic_id':return_data['id'], 'name_slug':slugify(return_data['name'])}),
            'Publishers')

        return_data['subscribers_link'] = '<a href="{}">{}</a>'.format(
            django_url_reverse('pubsub-topic-subscribers',
                kwargs={'cluster_id':self.req.zato.cluster_id,
                        'topic_id':return_data['id'], 'name_slug':slugify(return_data['name'])}),
            'Subscribers')

        item = self.req.zato.client.invoke('zato.pubsub.topic.get', {
            'cluster_id': self.req.zato.cluster_id,
            'id': return_data['id'],
        }).data.response

        return_data['has_gd'] = item.has_gd
        if item.get('last_pub_time'):
            return_data['last_pub_time'] = from_utc_to_user(item.last_pub_time+'+00:00', self.req.zato.user_profile)
        else:
            return_data['last_pub_time'] = None

        return_data['current_depth_link'] = """
            <a href="{}?cluster={}">{}</a>
            /
            {}
            """.format(

            # GD messages
            django_url_reverse('pubsub-topic-messages',
                kwargs={'topic_id':return_data['id'], 'name_slug':slugify(return_data['name'])}),
            self.req.zato.cluster_id,
            item.current_depth_gd,

            # Non-GD messages
            item.current_depth_gd,
            self.req.zato.cluster_id,
            item.current_depth_gd
        )

    def success_message(self, item):
        return 'Pub/sub topic `{}` {} successfully '.format(item.name, self.verb)

# ################################################################################################################################

class Create(_CreateEdit):
    url_name = 'pubsub-topic-create'
    service_name = 'zato.pubsub.topic.create'

# ################################################################################################################################

class Edit(_CreateEdit):
    url_name = 'pubsub-topic-edit'
    form_prefix = 'edit-'
    service_name = 'zato.pubsub.topic.edit'

# ################################################################################################################################

class Delete(_Delete):
    url_name = 'pubsub-topic-delete'
    error_message = 'Could not delete pub/sub topic'
    service_name = 'zato.pubsub.topic.delete'

# ################################################################################################################################

def topic_clear(req, cluster_id, topic_id):

    try:
        req.zato.client.invoke('zato.pubsub.topic.clear', {
            'cluster_id': cluster_id,
            'id': topic_id,
        })
    except Exception, e:
        return HttpResponseServerError(format_exc(e))
    else:
        msg = 'Cleared topic `{}`'.format(
            req.zato.client.invoke('zato.pubsub.topic.get', {
                'cluster_id': cluster_id,
                'id': topic_id,
            }).data.response.name)

    return HttpResponse(msg)

# ################################################################################################################################

class TopicPublishers(_Index):
    method_allowed = 'GET'
    url_name = 'pubsub-topic-publishers'
    template = 'zato/pubsub/topic-publishers.html'
    service_name = 'zato.pubsub.topic.get-publisher-list'
    output_class = PubSubEndpoint
    paginate = True

    class SimpleIO(_Index.SimpleIO):
        input_required = ('cluster_id', 'topic_id')
        output_required = ('endpoint_id', 'name', 'is_active', 'is_internal')
        output_optional = ('service_id', 'security_id', 'ws_channel_id', 'last_seen', 'last_pub_time', 'last_msg_id',
            'last_correl_id', 'last_in_reply_to', 'service_name', 'sec_name', 'ws_channel_name', 'pattern_matched',
            'conn_status', 'ext_client_id')
        output_repeated = True

    def on_before_append_item(self, item):
        item.last_seen = from_utc_to_user(item.last_seen+'+00:00', self.req.zato.user_profile)
        item.last_pub_time = from_utc_to_user(item.last_pub_time+'+00:00', self.req.zato.user_profile)
        item.client_html = get_client_html(item, item.security_id, self.req.zato.cluster_id)
        return item

    def handle(self):

        return {
            'topic_id': self.input.topic_id,
            'topic_name': self.req.zato.client.invoke(
                'zato.pubsub.topic.get', {
                    'cluster_id':self.req.zato.cluster_id,
                    'id':self.input.topic_id,
                }).data.response.name
        }

# ################################################################################################################################

class TopicSubscribers(_Index):
    method_allowed = 'GET'
    url_name = 'pubsub-topic-subscribers'
    template = 'zato/pubsub/topic-subscribers.html'
    service_name = 'zato.pubsub.topic.get-subscriber-list'
    output_class = PubSubEndpoint
    paginate = True

# ################################################################################################################################

class TopicMessages(_Index):
    method_allowed = 'GET'
    url_name = 'pubsub-topic-messages'
    template = 'zato/pubsub/topic-messages.html'
    service_name = 'zato.pubsub.topic.get-message-list'
    output_class = PubSubMessage
    paginate = True

    class SimpleIO(_Index.SimpleIO):
        input_required = ('cluster_id', 'topic_id')
        output_required = ('msg_id', 'pub_time', 'data_prefix_short', 'pattern_matched')
        output_optional = ('correl_id', 'in_reply_to', 'size', 'service_id', 'security_id', 'ws_channel_id',
            'service_name', 'sec_name', 'ws_channel_name', 'endpoint_id', 'endpoint_name')
        output_repeated = True

    def on_before_append_item(self, item):
        item.pub_time = from_utc_to_user(item.pub_time+'+00:00', self.req.zato.user_profile)
        item.endpoint_html = get_endpoint_html(item, self.req.zato.cluster_id)
        return item

    def handle(self):

        return {
            'topic_id': self.input.topic_id,
            'topic_name': self.req.zato.client.invoke(
                'zato.pubsub.topic.get', {
                    'cluster_id':self.req.zato.cluster_id,
                    'id':self.input.topic_id,
                }).data.response.name
        }

# ################################################################################################################################

class InRAMBacklog(_Index):
    method_allowed = 'GET'
    url_name = 'pubsub-topic-in-ram-backlog'
    template = 'zato/pubsub/topic-in-ram-backlog.html'
    service_name = 'zato.pubsub.topic.get-in-ram-backlog'
    output_class = PubSubMessage
    paginate = True

# ################################################################################################################################
