## 1. Test Infrastructure Setup
- [x] 1.1 Create backend/tests/ directory structure
- [x] 1.2 Create conftest.py with fixtures (users, teams, subscriptions)
- [x] 1.3 Create pytest configuration for Django
- [x] 1.4 Create test factories for models

## 2. Authentication Tests
- [x] 2.1 Test user registration endpoint
- [x] 2.2 Test JWT token obtain/refresh/verify
- [x] 2.3 Test API key authentication
- [x] 2.4 Test invalid credential handling
- [x] 2.5 Test token expiration and refresh flow

## 3. Team Management Tests
- [x] 3.1 Test team CRUD operations
- [x] 3.2 Test team member management
- [x] 3.3 Test invitation workflow
- [x] 3.4 Test role changes
- [x] 3.5 Test member removal

## 4. Permission Tests
- [x] 4.1 Test owner-only actions
- [x] 4.2 Test admin-level permissions
- [x] 4.3 Test member-level access
- [x] 4.4 Test cross-company isolation
- [x] 4.5 Test unauthenticated access

## 5. Billing Tests
- [x] 5.1 Test plan listing
- [x] 5.2 Test checkout session creation
- [x] 5.3 Test webhook signature verification
- [x] 5.4 Test subscription lifecycle events
- [x] 5.5 Test usage tracking and limits

## 6. Frontend Unit Tests
- [x] 6.1 Setup Vitest configuration
- [x] 6.2 Test auth components (login, register forms)
- [x] 6.3 Test dashboard components
- [x] 6.4 Test API client and auth store
- [x] 6.5 Test route protection logic

## 7. E2E Automation Tests
- [x] 7.1 Setup Playwright configuration
- [x] 7.2 Test complete signup flow
- [x] 7.3 Test login/logout cycle
- [x] 7.4 Test team management flow
- [x] 7.5 Test billing/subscription flow
