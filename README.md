# TEXT Backend - The Obsidian Gallery

A Django REST Framework backend for TEXT, a micro-blogging platform for literary enthusiasts.

## Features

- User authentication with JWT tokens
- Create, read, update, delete posts (max 288 characters)
- Like and comment on posts
- Follow/unfollow users
- Personalized feed from followed users
- Genre-based post filtering
- Full user profiles with followers/following counts

## Prerequisites

- Python 3.11+
- pip or pipenv

## Installation

1. **Clone the repository**
```bash
cd backend
```

2. **Create a virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Create a .env file** (copy from .env.example)
```bash
cp .env.example .env
```

5. **Run migrations**
```bash
python manage.py migrate
```

6. **Create a superuser** (optional, for Django admin)
```bash
python manage.py createsuperuser
```

7. **Seed the database with test data** (optional)
```bash
python manage.py seed_data
```

8. **Run the development server**
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/`

## API Endpoints

### Authentication

- `POST /api/auth/register/` - Register a new user
- `POST /api/auth/login/` - Login and get JWT tokens
- `POST /api/auth/logout/` - Logout
- `POST /api/auth/token/refresh/` - Refresh access token

### Users

- `GET /api/users/{username}/` - Get user profile
- `PUT /api/users/{username}/` - Update own profile
- `GET /api/users/{username}/posts/` - Get user's posts
- `POST /api/users/{username}/follow/` - Follow/unfollow user
- `GET /api/users/{username}/followers/` - Get user's followers
- `GET /api/users/{username}/following/` - Get users that this user follows

### Posts

- `GET /api/posts/` - Get all posts (paginated)
- `POST /api/posts/` - Create a new post
- `GET /api/posts/{id}/` - Get post details
- `PUT /api/posts/{id}/` - Update post
- `DELETE /api/posts/{id}/` - Delete post
- `POST /api/posts/{id}/like/` - Like/unlike a post
- `GET /api/posts/{id}/comments/` - Get post comments
- `POST /api/posts/{id}/add_comment/` - Add comment to post
- `GET /api/posts/{id}/likes/` - Get users who liked the post

### Feed

- `GET /api/feed/` - Get personalized feed (posts from followed users)

## Testing the API

You can test the API using:

### cURL Examples

**Register a new user**
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass123","password2":"testpass123"}'
```

**Login**
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123"}'
```

**Create a post**
```bash
curl -X POST http://localhost:8000/api/posts/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"My first post!","genre":"thought"}'
```

### Using Postman

1. Download and install [Postman](https://www.postman.com/downloads/)
2. Import the collection or manually create requests
3. For authenticated endpoints, add the JWT token in the Authorization header

### Using Django REST Framework's Web Interface

Navigate to any endpoint in your browser and use the web interface to make requests.

## Database Models

### User (CustomUser)
- username: CharField
- email: EmailField
- bio: CharField (max 260 characters)
- avatar: ImageField
- date_joined: DateTimeField

### Post
- author: ForeignKey(User)
- content: CharField (max 288 characters)
- genre: Choice field (Horror, Funny, Story, Thought, Other)
- created_at: DateTimeField
- updated_at: DateTimeField

### Like
- user: ForeignKey(User)
- post: ForeignKey(Post)
- created_at: DateTimeField
- Constraint: unique(user, post)

### Comment
- author: ForeignKey(User)
- post: ForeignKey(Post)
- content: TextField
- created_at: DateTimeField

### Follow
- follower: ForeignKey(User)
- following: ForeignKey(User)
- created_at: DateTimeField
- Constraint: unique(follower, following)

## Project Structure

```
backend/
├── manage.py
├── requirements.txt
├── .env.example
├── README.md
├── db.sqlite3
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── users/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── permissions.py
│   │   ├── apps.py
│   │   ├── __init__.py
│   │   └── management/
│   │       └── commands/
│   │           └── seed_data.py
│   ├── posts/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── apps.py
│   │   └── __init__.py
│   └── feed/
│       ├── views.py
│       ├── urls.py
│       ├── apps.py
│       └── __init__.py
```

## Configuration

### Environment Variables

The following environment variables can be set in `.env`:

- `SECRET_KEY` - Django secret key (change in production!)
- `DEBUG` - Debug mode (set to False in production)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts
- `CORS_ALLOWED_ORIGINS` - Comma-separated list of CORS origins

### JWT Configuration

JWT tokens are configured in `config/settings.py`:
- Access token lifetime: 1 hour
- Refresh token lifetime: 7 days

## Pagination

All list endpoints are paginated with 10 items per page. Use the `?page=N` parameter to navigate pages.

## Filtering and Search

Posts can be filtered and searched by:
- Content
- Author username
- Genre

Example: `GET /api/posts/?search=horror&genre=horror`

## Error Handling

The API returns standard HTTP status codes and JSON error messages:

```json
{
  "error": "Error message here"
}
```

## Performance Optimizations

- Database query optimization with `select_related()` and `prefetch_related()`
- Proper indexing on frequently queried fields
- Pagination to limit response sizes

## Security Notes

- JWT authentication for protected endpoints
- CORS configuration for cross-origin requests
- Password validation and hashing with Django's built-in tools
- Read-only fields for sensitive data

## Troubleshooting

### Database Migration Issues
```bash
python manage.py makemigrations
python manage.py migrate
```

### Permission Denied Errors
Make sure you're including the JWT token in the Authorization header:
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### CORS Errors
Update `CORS_ALLOWED_ORIGINS` in `.env` to include your frontend URL.

## Development Notes

- Uses SQLite for development (suitable for testing)
- Can be easily switched to PostgreSQL for production
- All endpoints follow REST conventions
- Comprehensive error handling and validation

## License

MIT
