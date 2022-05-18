from django.core.management.base import BaseCommand
from django.utils import timezone

from post_deploy.models import PostDeployAction
from post_deploy.local_utils import initialize_actions, get_context_manager, get_scheduler_manager


class Command(BaseCommand):
    help = "Execute post deployment actions."

    def __init__(self):
        super(Command, self).__init__()
        self.context_manager = None

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser=parser)
        parser.add_argument('--report', const=True, action='store_const',
                            help="Print the status of all actions.")
        parser.add_argument('--auto', const=True, action='store_const',
                            help="Execute all pending actions that have auto=True (default setting).")
        parser.add_argument('--all', const=True, action='store_const',
                            help="Execute all pending actions no matter the value of auto.")
        parser.add_argument('--one', help="Execute one of the actions.")

    def handle(self, *args, **options):
        self.context_manager = get_context_manager(None)
        with self.context_manager.execute():
            todo_list = []
            for todo in ['report', 'auto', 'all', 'one']:
                if options.get(todo):
                    todo_list.append(todo)

            if len(todo_list) != 1:
                self.stderr.write("Provide 1 todo at a time.\n")
                return self.do_help()

            initialize_actions()

            if options['report']:
                return self.do_report()

            if PostDeployAction.objects.running().exists():
                self.stderr.write("Please wait until all tasks are completed.")
                return

            if options['auto']:
                return self.do_execute(PostDeployAction.objects.todo())

            if options['all']:
                return self.do_execute(PostDeployAction.objects.unprocessed())

            if options['one']:
                return self.do_execute(PostDeployAction.objects.filter(id=[options['one']]))

    def do_help(self):
        self.print_help("manage.py", "post_deploy")

    def do_report(self):
        if PostDeployAction.objects.unprocessed().count() == 0:
            self.stdout.write("No pending actions found.")

        if PostDeployAction.objects.todo().exists():
            self.stdout.write("Pending actions that can run automatically:")
            for action in PostDeployAction.objects.todo():
                self.stdout.write("* %s" % action.id)

        if PostDeployAction.objects.manual().exists():
            self.stdout.write("\nPending actions that need starting manually:")
            for action in PostDeployAction.objects.manual():
                if action.message:
                    self.stdout.write(f"* {action.id} ({action.message})")
                else:
                    self.stdout.write(f"* {action.id}")

        if PostDeployAction.objects.running().exists():
            self.stdout.write("\nCurrently running actions:")
            for action in PostDeployAction.objects.running():
                self.stdout.write(f"* {action.id} ({action.started_at})")

        if PostDeployAction.objects.with_errors().exists():
            self.stdout.write("\nActions that failed:")
            for action in PostDeployAction.objects.with_errors():
                self.stdout.write(f"* {action.id} ({action.completed_at})")
                self.stdout.write(f"  {action.message}")

        if PostDeployAction.objects.completed().order_by('-completed_at').exists():
            self.stdout.write("\nCompleted actions:")
            for action in PostDeployAction.objects.completed().order_by('-completed_at'):
                self.stdout.write(f"* {action.id} ({action.completed_at})")

    def do_execute(self, qs):
        if qs.count() > 0:
            qs.update(
                started_at=timezone.localtime(),
                completed_at=None,
                message=None,
                done=False
            )

            self.stdout.write("Scheduled execute:")
            for id in qs.ids():
                self.stdout.write(f"* {id}")

            task_id = get_scheduler_manager().schedule(qs.ids(), self.context_manager.default_parameters())
            qs.update(
                task_id=task_id
            )