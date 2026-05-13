from django.core.management.base import BaseCommand

from events.services import dispatch_pending_events


class Command(BaseCommand):
    help = "Dispatch a bounded batch of pending local outbox events."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--dispatcher-name", default="management-command")

    def handle(self, *args, **options):
        dispatched = dispatch_pending_events(
            dispatcher_name=options["dispatcher_name"],
            batch_size=options["batch_size"],
        )
        self.stdout.write(f"Dispatched {dispatched} event(s).")
