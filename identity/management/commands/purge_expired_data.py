
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from identity.models import AnonymousProfile
from workspace.models import Board

class Command(BaseCommand):
    help = 'Soft deletes inactive ghost profiles/boards after 30 days, and permanently deletes them 7 days later.'

    def handle(self, *args, **options):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)

        self.stdout.write("Starting purge check...") # User feedback

        # ------------------------------------------------------------------
        # TRACK A: GHOST PROFILE LIFECYCLE
        # ------------------------------------------------------------------
        
        # 1. Soft Delete (Day 30)
        profiles_to_soft_delete = AnonymousProfile.objects.filter(
            created_at__lt=thirty_days_ago, 
            is_soft_deleted=False
        )
        soft_count = profiles_to_soft_delete.update(
            is_soft_deleted=True, 
            soft_deleted_at=now
        )
        if soft_count:
            self.stdout.write(self.style.WARNING(f"Soft-deleted {soft_count} expired Ghost Profiles."))

        # 2. Hard Delete (Day 37)
        profiles_to_hard_delete = AnonymousProfile.objects.filter(
            is_soft_deleted=True,
            soft_deleted_at__lt=seven_days_ago
        )
        hard_count = profiles_to_hard_delete.count() 
        profiles_to_hard_delete.delete() 
        if hard_count:
            self.stdout.write(self.style.SUCCESS(f"Permanently purged {hard_count} Ghost Profiles."))

        # ------------------------------------------------------------------
        # TRACK B: UNCLAIMED BOARD LIFECYCLE
        # ------------------------------------------------------------------
        
        boards_to_soft_delete = Board.objects.filter(
            created_at__lt=thirty_days_ago,
            is_soft_deleted=False,
            creator_ghost__user__isnull=True 
        )
        board_soft_count = boards_to_soft_delete.update(
            is_soft_deleted=True,
            soft_deleted_at=now
        )
        if board_soft_count:
            self.stdout.write(self.style.WARNING(f"Soft-deleted {board_soft_count} unclaimed Boards."))

        boards_to_hard_delete = Board.objects.filter(
            is_soft_deleted=True,
            soft_deleted_at__lt=seven_days_ago
        )
        board_hard_count = boards_to_hard_delete.count()
        boards_to_hard_delete.delete()
        if board_hard_count:
            self.stdout.write(self.style.SUCCESS(f"Permanently purged {board_hard_count} unclaimed Boards."))

        if not any([soft_count, hard_count, board_soft_count, board_hard_count]):
             self.stdout.write(self.style.SUCCESS("No expired data found. System clean."))
