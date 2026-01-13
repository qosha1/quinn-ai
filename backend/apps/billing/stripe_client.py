"""
Stripe integration service for subscription management.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.teams.models import Company
from apps.billing.models import Subscription, Plan, Invoice

logger = logging.getLogger(__name__)

# Initialize Stripe with API key from settings
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """
    Service class for Stripe operations.

    Handles all interactions with the Stripe API including customer management,
    subscriptions, checkout sessions, and customer portal.
    """

    @staticmethod
    def create_customer(company: Company) -> str:
        """
        Create a Stripe customer for a company.

        Args:
            company: Company instance to create customer for

        Returns:
            Stripe customer ID

        Raises:
            stripe.StripeError: If customer creation fails
        """
        try:
            customer = stripe.Customer.create(
                name=company.name,
                metadata={
                    "company_id": str(company.id),
                    "company_slug": company.slug,
                }
            )
            logger.info(f"Created Stripe customer {customer.id} for company {company.id}")
            return customer.id
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe customer for company {company.id}: {e}")
            raise

    @staticmethod
    def get_or_create_customer(company: Company) -> str:
        """
        Get existing Stripe customer ID or create a new one.

        Args:
            company: Company instance

        Returns:
            Stripe customer ID
        """
        # Check if company has an active subscription with customer ID
        if hasattr(company, 'subscription') and company.subscription.stripe_customer_id:
            return company.subscription.stripe_customer_id

        # Create new customer
        return StripeService.create_customer(company)

    @staticmethod
    def create_checkout_session(
        company: Company,
        plan: Plan,
        success_url: str,
        cancel_url: str,
        trial_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription.

        Args:
            company: Company subscribing to the plan
            plan: Plan to subscribe to
            success_url: URL to redirect to on success
            cancel_url: URL to redirect to on cancellation
            trial_days: Optional number of trial days

        Returns:
            Dictionary with session ID and URL

        Raises:
            stripe.StripeError: If session creation fails
        """
        try:
            customer_id = StripeService.get_or_create_customer(company)

            session_params = {
                "customer": customer_id,
                "mode": "subscription",
                "line_items": [
                    {
                        "price": plan.stripe_price_id,
                        "quantity": 1,
                    }
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "company_id": str(company.id),
                    "plan_id": str(plan.id),
                },
            }

            # Add trial if specified
            if trial_days:
                session_params["subscription_data"] = {
                    "trial_period_days": trial_days
                }

            session = stripe.checkout.Session.create(**session_params)

            logger.info(
                f"Created checkout session {session.id} for company {company.id}, plan {plan.slug}"
            )

            return {
                "session_id": session.id,
                "url": session.url,
            }
        except stripe.StripeError as e:
            logger.error(f"Failed to create checkout session for company {company.id}: {e}")
            raise

    @staticmethod
    def create_portal_session(company: Company, return_url: str) -> str:
        """
        Create a Stripe Customer Portal session.

        Args:
            company: Company to create portal for
            return_url: URL to return to from portal

        Returns:
            Portal session URL

        Raises:
            stripe.StripeError: If portal creation fails
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        try:
            session = stripe.billing_portal.Session.create(
                customer=company.subscription.stripe_customer_id,
                return_url=return_url,
            )

            logger.info(f"Created portal session for company {company.id}")
            return session.url
        except stripe.StripeError as e:
            logger.error(f"Failed to create portal session for company {company.id}: {e}")
            raise

    @staticmethod
    def cancel_subscription(subscription: Subscription, immediate: bool = False) -> None:
        """
        Cancel a subscription.

        Args:
            subscription: Subscription to cancel
            immediate: If True, cancel immediately; if False, at period end

        Raises:
            stripe.StripeError: If cancellation fails
        """
        try:
            if immediate:
                stripe.Subscription.delete(subscription.stripe_subscription_id)
                subscription.status = Subscription.Status.CANCELLED
                subscription.cancel_at_period_end = False
            else:
                stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True,
                )
                subscription.cancel_at_period_end = True

            subscription.save()
            logger.info(
                f"Cancelled subscription {subscription.id} "
                f"({'immediate' if immediate else 'at period end'})"
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to cancel subscription {subscription.id}: {e}")
            raise

    @staticmethod
    def get_invoices(company: Company, limit: int = 10) -> list:
        """
        Retrieve invoices for a company from Stripe.

        Args:
            company: Company to get invoices for
            limit: Maximum number of invoices to retrieve

        Returns:
            List of Stripe invoice objects

        Raises:
            stripe.StripeError: If retrieval fails
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        try:
            invoices = stripe.Invoice.list(
                customer=company.subscription.stripe_customer_id,
                limit=limit,
            )
            return invoices.data
        except stripe.StripeError as e:
            logger.error(f"Failed to get invoices for company {company.id}: {e}")
            raise

    @staticmethod
    @transaction.atomic
    def sync_subscription(stripe_subscription: Dict[str, Any]) -> Subscription:
        """
        Sync subscription data from Stripe webhook.

        Args:
            stripe_subscription: Stripe subscription object as dict

        Returns:
            Updated or created Subscription instance

        Raises:
            ValueError: If company or plan not found
        """
        # Extract metadata
        metadata = stripe_subscription.get("metadata", {})
        company_id = metadata.get("company_id")

        if not company_id:
            raise ValueError("Subscription missing company_id in metadata")

        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            raise ValueError(f"Company {company_id} not found")

        # Get plan from subscription items
        items = stripe_subscription.get("items", {}).get("data", [])
        if not items:
            raise ValueError("Subscription has no items")

        stripe_price_id = items[0]["price"]["id"]

        try:
            plan = Plan.objects.get(stripe_price_id=stripe_price_id)
        except Plan.DoesNotExist:
            raise ValueError(f"Plan with price ID {stripe_price_id} not found")

        # Convert timestamps
        current_period_start = datetime.fromtimestamp(
            stripe_subscription["current_period_start"],
            tz=timezone.utc
        )
        current_period_end = datetime.fromtimestamp(
            stripe_subscription["current_period_end"],
            tz=timezone.utc
        )

        trial_start = None
        trial_end = None
        if stripe_subscription.get("trial_start"):
            trial_start = datetime.fromtimestamp(
                stripe_subscription["trial_start"],
                tz=timezone.utc
            )
        if stripe_subscription.get("trial_end"):
            trial_end = datetime.fromtimestamp(
                stripe_subscription["trial_end"],
                tz=timezone.utc
            )

        # Update or create subscription
        subscription, created = Subscription.objects.update_or_create(
            stripe_subscription_id=stripe_subscription["id"],
            defaults={
                "company": company,
                "plan": plan,
                "stripe_customer_id": stripe_subscription["customer"],
                "status": stripe_subscription["status"],
                "current_period_start": current_period_start,
                "current_period_end": current_period_end,
                "cancel_at_period_end": stripe_subscription.get("cancel_at_period_end", False),
                "trial_start": trial_start,
                "trial_end": trial_end,
            }
        )

        action = "Created" if created else "Updated"
        logger.info(
            f"{action} subscription {subscription.id} for company {company.id}"
        )

        return subscription

    @staticmethod
    @transaction.atomic
    def sync_invoice(stripe_invoice: Dict[str, Any]) -> Invoice:
        """
        Sync invoice data from Stripe webhook.

        Args:
            stripe_invoice: Stripe invoice object as dict

        Returns:
            Updated or created Invoice instance

        Raises:
            ValueError: If subscription not found
        """
        subscription_id = stripe_invoice.get("subscription")

        if not subscription_id:
            raise ValueError("Invoice missing subscription ID")

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        except Subscription.DoesNotExist:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Convert timestamps
        period_start = datetime.fromtimestamp(
            stripe_invoice["period_start"],
            tz=timezone.utc
        )
        period_end = datetime.fromtimestamp(
            stripe_invoice["period_end"],
            tz=timezone.utc
        )

        paid_at = None
        if stripe_invoice.get("status_transitions", {}).get("paid_at"):
            paid_at = datetime.fromtimestamp(
                stripe_invoice["status_transitions"]["paid_at"],
                tz=timezone.utc
            )

        # Convert amount from cents to dollars
        amount = stripe_invoice["amount_paid"] / 100

        # Update or create invoice
        invoice, created = Invoice.objects.update_or_create(
            stripe_invoice_id=stripe_invoice["id"],
            defaults={
                "company": subscription.company,
                "subscription": subscription,
                "amount": amount,
                "currency": stripe_invoice.get("currency", "usd"),
                "status": stripe_invoice["status"],
                "invoice_pdf": stripe_invoice.get("invoice_pdf", ""),
                "period_start": period_start,
                "period_end": period_end,
                "paid_at": paid_at,
            }
        )

        action = "Created" if created else "Updated"
        logger.info(
            f"{action} invoice {invoice.id} for subscription {subscription.id}"
        )

        return invoice
