## 1. Users App
- [x] 1.1 Create backend/apps/users/models.py with custom User
- [x] 1.2 Create backend/apps/users/api/views.py UserViewSet
- [x] 1.3 Create backend/apps/users/api/serializers.py
- [x] 1.4 Create backend/apps/users/managers.py

## 2. Teams App
- [x] 2.1 Create backend/apps/teams/models.py (Company, Team, TeamMember, TeamInvitation)
- [x] 2.2 Create backend/apps/teams/api/views.py
- [x] 2.3 Create backend/apps/teams/api/serializers.py
- [x] 2.4 Create backend/apps/teams/api/permissions.py
- [x] 2.5 Create backend/apps/teams/signals.py for auto team creation

## 3. Authentication App
- [x] 3.1 Create backend/apps/authentication/models.py (APIKey)
- [x] 3.2 Create backend/apps/authentication/backends.py
- [x] 3.3 Create backend/apps/authentication/api/views.py
- [x] 3.4 Configure JWT in settings

## 4. Permissions
- [x] 4.1 Create IsCompanyMember permission
- [x] 4.2 Create IsTeamMember permission
- [x] 4.3 Create role-based permission classes
- [x] 4.4 Create TeamOwnedMixin for querysets
