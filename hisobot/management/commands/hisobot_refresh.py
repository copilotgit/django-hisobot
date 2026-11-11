from django.core.management.base import BaseCommand, CommandError

from hisobot import report
from hisobot.hemis import HemisError


class Command(BaseCommand):
    help = "HEMIS'dan auditoriyalar, darslar va imtihonlarni yuklab, hisobotni yangilaydi (cron uchun qulay)."

    def handle(self, *args, **options):
        try:
            report.refresh(log=self.stdout.write)
        except (HemisError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Tayyor."))
