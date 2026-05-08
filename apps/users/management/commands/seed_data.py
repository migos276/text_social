from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.posts.models import Post, Like, Comment
from apps.users.models import Follow

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with test data'
    
    def handle(self, *args, **options):
        # Clear existing data
        User.objects.all().delete()
        Post.objects.all().delete()
        Like.objects.all().delete()
        Comment.objects.all().delete()
        Follow.objects.all().delete()
        
        # Create test users
        users_data = [
            {'username': 'alice', 'email': 'alice@example.com', 'bio': 'Literary enthusiast and writer'},
            {'username': 'bob', 'email': 'bob@example.com', 'bio': 'Horror stories lover'},
            {'username': 'charlie', 'email': 'charlie@example.com', 'bio': 'Thought-provoking ideas'},
            {'username': 'diana', 'email': 'diana@example.com', 'bio': 'Comedy writer'},
            {'username': 'eva', 'email': 'eva@example.com', 'bio': 'Storyteller'},
        ]
        
        users = []
        for user_data in users_data:
            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                password='testpass123',
                bio=user_data['bio']
            )
            users.append(user)
        
        # Create follow relationships
        Follow.objects.create(follower=users[0], following=users[1])
        Follow.objects.create(follower=users[0], following=users[2])
        Follow.objects.create(follower=users[1], following=users[3])
        Follow.objects.create(follower=users[2], following=users[0])
        
        # Create test posts
        posts_data = [
            {'author': users[0], 'content': 'The night was silent, only the echo of my heartbeat.', 'genre': 'thought'},
            {'author': users[1], 'content': 'In the darkness, a shadow moved. Was it real or just my fear?', 'genre': 'horror'},
            {'author': users[2], 'content': 'Why do we fear the unknown when the known is far more dangerous?', 'genre': 'thought'},
            {'author': users[3], 'content': 'I tried to be serious, but my face had other plans.', 'genre': 'funny'},
            {'author': users[0], 'content': 'Once upon a time, there was a girl who discovered magic in words.', 'genre': 'story'},
            {'author': users[4], 'content': 'The sunset painted the sky in shades of hope and melancholy.', 'genre': 'thought'},
            {'author': users[1], 'content': 'They said the house was haunted. But nothing compared to my dreams.', 'genre': 'horror'},
            {'author': users[3], 'content': 'Coffee is a hug in a mug, and I am hugging myself constantly.', 'genre': 'funny'},
        ]
        
        posts = []
        for post_data in posts_data:
            post = Post.objects.create(**post_data)
            posts.append(post)
        
        # Create likes
        Like.objects.create(user=users[0], post=posts[1])
        Like.objects.create(user=users[0], post=posts[3])
        Like.objects.create(user=users[1], post=posts[0])
        Like.objects.create(user=users[2], post=posts[4])
        Like.objects.create(user=users[3], post=posts[0])
        Like.objects.create(user=users[4], post=posts[2])
        Like.objects.create(user=users[0], post=posts[5])
        
        # Create comments
        Comment.objects.create(
            author=users[1],
            post=posts[0],
            content='Beautiful expression of the soul!'
        )
        Comment.objects.create(
            author=users[2],
            post=posts[1],
            content='This gave me chills!'
        )
        Comment.objects.create(
            author=users[3],
            post=posts[3],
            content='Haha, so relatable!'
        )
        Comment.objects.create(
            author=users[0],
            post=posts[7],
            content='Best analogy ever!'
        )
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded database with test data'))
        self.stdout.write(f'Created {len(users)} users')
        self.stdout.write(f'Created {len(posts)} posts')
        self.stdout.write(f'Created {Like.objects.count()} likes')
        self.stdout.write(f'Created {Comment.objects.count()} comments')
        self.stdout.write(f'Created {Follow.objects.count()} follow relationships')
