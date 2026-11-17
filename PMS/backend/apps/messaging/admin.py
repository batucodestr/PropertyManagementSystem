from django.contrib import admin

from .models import Conversation, Message, MessageTemplate, ScheduledMessage

admin.site.register(MessageTemplate)
admin.site.register(ScheduledMessage)
admin.site.register(Conversation)
admin.site.register(Message)
