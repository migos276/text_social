from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Tag(models.Model):
    """Normalized tags used by recommendation and discovery."""

    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'posts_tag'
        ordering = ['name']

    def __str__(self):
        return self.name


class Post(models.Model):
    """Model for literary posts"""
    
    GENRE_CHOICES = [
        ('horror', 'Horreur'),
        ('funny', 'Drôle'),
        ('story', 'Histoire'),
        ('thought', 'Pensée'),
        ('other', 'Autre'),
    ]
    
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content = models.CharField(max_length=288)
    genre = models.CharField(max_length=20, choices=GENRE_CHOICES, default='other')
    background_color = models.CharField(max_length=7, default='#1A1A1A')
    audio_file = models.FileField(upload_to='posts/audio/', blank=True, null=True)
    audio_title = models.CharField(max_length=255, blank=True, default='')
    audio_duration_ms = models.PositiveIntegerField(default=0)
    tags = models.ManyToManyField(Tag, related_name='posts', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'posts_post'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['genre', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.author.username}: {self.content[:50]}"
    
    @property
    def likes_count(self):
        return self.likes.count()
    
    @property
    def comments_count(self):
        return self.comments.count()


class Like(models.Model):
    """Model for liking posts"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='likes')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'post')
        db_table = 'posts_like'
        indexes = [
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} likes {self.post.id}"


class Bookmark(models.Model):
    """Model for saving posts as favorites"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        db_table = 'posts_bookmark'
        indexes = [
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} bookmarked {self.post.id}"


class Comment(models.Model):
    """Model for commenting on posts"""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'posts_comment'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]
    
    def __str__(self):
        return f"Comment by {self.author.username} on post {self.post.id}"
