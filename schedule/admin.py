from django.contrib import admin

from .models import Project, Reservation, Slot


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at', 'slots_until']


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ['project', 'start', 'closed']
    list_filter = ['project', 'closed']


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['slot', 'full_name', 'name', 'mail', 'paid']
    list_filter = ['slot__project', 'paid']
