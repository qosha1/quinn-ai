# Landing Page Specification

## ADDED Requirements

### Requirement: NextJS 15 Setup
The landing page SHALL use NextJS 15 with App Router and React 19.

#### Scenario: Development server
- **WHEN** developer runs `npm run dev`
- **THEN** landing page is accessible at http://localhost:3000
- **AND** hot reload works for component changes

### Requirement: Tailwind with shadcn/ui
The landing page SHALL use Tailwind CSS with shadcn/ui components.

#### Scenario: Theme customization
- **GIVEN** tailwind.config.js with CSS variables
- **WHEN** --primary color is changed
- **THEN** all primary-colored components update

### Requirement: Dark Mode Support
The landing page SHALL support light and dark themes.

#### Scenario: Theme toggle
- **WHEN** user clicks theme toggle
- **THEN** theme switches between light and dark
- **AND** preference is persisted in localStorage

### Requirement: Hero Section
The landing page SHALL have a hero section with headline, subheadline, and CTA.

#### Scenario: Hero rendering
- **WHEN** page loads
- **THEN** hero section is visible above the fold
- **AND** primary CTA button links to signup

### Requirement: Pricing Section
The landing page SHALL display pricing tiers with features.

#### Scenario: Pricing display
- **WHEN** user views pricing section
- **THEN** all plans are visible with prices
- **AND** each plan shows included features
- **AND** CTA buttons link to checkout

### Requirement: SEO Optimization
The landing page SHALL include SEO metadata and structured data.

#### Scenario: Search engine indexing
- **WHEN** search engine crawls page
- **THEN** meta tags provide title, description, og:image
- **AND** sitemap.xml lists all public pages
- **AND** robots.txt allows indexing

### Requirement: Responsive Design
The landing page SHALL be fully responsive.

#### Scenario: Mobile view
- **WHEN** page is viewed on mobile device
- **THEN** layout adapts to screen width
- **AND** navigation becomes hamburger menu
- **AND** all content is readable
