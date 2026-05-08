from django.core.management.base import BaseCommand

from apps.feed.services import detect_viral_posts, evaluate_distribution_pools


class Command(BaseCommand):
    help = 'Evaluate recommendation pools and detect viral posts.'

    def handle(self, *args, **options):
        moved_posts = evaluate_distribution_pools()
        viral_posts = detect_viral_posts()
        self.stdout.write(
            self.style.SUCCESS(
                f'Pool evaluation completed. Graduated posts: {len(moved_posts)}. Viral posts: {len(viral_posts)}'
            )
        )
