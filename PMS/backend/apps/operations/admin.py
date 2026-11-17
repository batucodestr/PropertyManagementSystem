from django.contrib import admin
from .models import GeneralTask, HouseKeepingTasks, StayRecord, TaskPhoto

admin.site.register(GeneralTask)
admin.site.register(HouseKeepingTasks)
admin.site.register(StayRecord)
admin.site.register(TaskPhoto)
