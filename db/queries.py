from datetime import datetime
from typing import Any, List, Optional

from agents import function_tool

from .database import db


def _normalize_choice(value: str, choices: List[str]) -> Optional[str]:
    lowered = value.strip().lower()
    for option in choices:
        if lowered == option.lower():
            return option
    return None


ORDER_STATUSES = [
    "Pending",
    "Paid",
    "Cancelled",
    "Refunded",
    "PartiallyRefunded",
    "Fulfilled",
]

PAYMENT_STATUSES = [
    "Pending",
    "Authorized",
    "Captured",
    "Failed",
    "Cancelled",
]

ITEM_TYPES = ["Product", "Ticket", "Party"]
PARTY_STATUSES = [
    "Pending",
    "Confirmed",
    "Cancelled",
    "Completed",
    "Refunded",
    "Rescheduled",
]


@function_tool
def create_customer_profile(
    full_name: str,
    email: str,
    phone: str,
    guardian_name: str,
    child_name: str,
    child_birthdate: str,
    notes: str = "",
) -> str:
    """
    Create a customer record with the provided details and return the new customer_id.
    All fields should be collected during checkout.
    """
    if not full_name.strip():
        return "full_name is required."

    try:
        birthdate_value = child_birthdate if child_birthdate else None
        if birthdate_value:
            # Validate format
            datetime.strptime(child_birthdate, "%Y-%m-%d")
    except ValueError:
        return "child_birthdate must use YYYY-MM-DD format."

    try:
        data = {
            "full_name": full_name.strip(),
            "email": email.strip() or None,
            "phone": phone.strip() or None,
            "guardian_name": guardian_name.strip() or None,
            "child_name": child_name.strip() or None,
            "child_birthdate": birthdate_value,
            "notes": notes.strip() or None,
        }
        result = db.insert("customers", data)
        if result and len(result) > 0:
            customer_id = result[0].get("customer_id")
            return f"Customer profile created. customer_id={customer_id}"
        return "Failed to create customer profile."
    except Exception as e:
        return f"Error creating customer: {e}"


@function_tool
def search_products(
    keyword: str = "",
    category: str = "",
    age_group: str = "",
    max_results: int = 5,
) -> str:
    """
    Look up active products that match optional filters.
    """
    max_results = max(1, min(max_results, 20))
    
    try:
        # Build filters for Supabase
        filters = ["is_active=eq.true"]
        
        endpoint = f"products?select=product_id,product_name,category,age_group,price_usd,stock_qty&{filters[0]}"
        
        if keyword:
            # Using or filter for keyword search
            endpoint += f"&or=(product_name.ilike.*{keyword}*,brand.ilike.*{keyword}*,sku.ilike.*{keyword}*)"
        if category:
            endpoint += f"&category=ilike.*{category}*"
        if age_group:
            endpoint += f"&age_group=ilike.*{age_group}*"
        
        endpoint += f"&order=stock_qty.desc,price_usd.asc&limit={max_results}"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No matching toys found."

        lines = ["Matching toys:"]
        for row in rows:
            age_text = f" for ages {row['age_group']}" if row.get('age_group') else ""
            lines.append(
                f"- #{row['product_id']} {row['product_name']} ({row.get('category') or 'Uncategorized'}{age_text}) - "
                f"${row['price_usd']:.2f}, stock {row['stock_qty']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching products: {e}"


@function_tool
def get_product_details(product_id: int) -> str:
    """
    Return enriched product information, including description and features.
    """
    try:
        row = db.get_by_id("products", "product_id", product_id)
        
        if not row or not row.get("is_active"):
            return "Toy not found or inactive."

        details = [
            f"{row['product_name']} details:",
            f"- Brand: {row.get('brand') or 'N/A'}",
            f"- Category: {row.get('category') or 'N/A'}",
            f"- Age group: {row.get('age_group') or 'All ages'}",
            f"- Material: {row.get('material') or 'Not specified'}",
            f"- Color: {row.get('color') or 'Various'}",
            f"- Price: ${row['price_usd']:.2f}",
            f"- Stock: {row['stock_qty']}",
        ]
        if row.get('rating') is not None:
            details.append(f"- Rating: {row['rating']:.2f}/5")
        if row.get('country'):
            details.append(f"- Country of origin: {row['country']}")
        if row.get('description'):
            details.append(f"\nDescription:\n{row['description'].strip()}")
        if row.get('features'):
            details.append(f"\nFeatures:\n{row['features'].strip()}")
        return "\n".join(details)
    except Exception as e:
        return f"Error getting product details: {e}"


@function_tool
def get_ticket_pricing(location_name: str = "") -> str:
    """
    Summarize active ticket pricing, optionally filtered by location name.
    """
    try:
        endpoint = "ticket_types?select=name,base_price_usd,requires_waiver,requires_grip_socks,location_id,locations(name)&is_active=eq.true&order=base_price_usd"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No ticket options available."

        lines = ["Admission ticket pricing:"]
        for row in rows:
            location = row.get("locations", {}).get("name") if row.get("locations") else "All Locations"
            if location_name and location_name.lower() not in (location or "").lower():
                continue
            
            tags: List[str] = []
            if row.get("requires_waiver"):
                tags.append("waiver required")
            if row.get("requires_grip_socks"):
                tags.append("grip socks required")
            tag_text = f" ({', '.join(tags)})" if tags else ""
            lines.append(f"- {location}: {row['name']} - ${row['base_price_usd']:.2f}{tag_text}")
        
        if len(lines) == 1:
            return "No ticket options available for that location."
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting ticket pricing: {e}"


@function_tool
def list_party_packages(location_name: str = "") -> str:
    """
    List party packages with pricing and inclusions.
    """
    try:
        endpoint = "party_packages?select=*,locations(name),package_inclusions(item_name,quantity)&is_active=eq.true&order=price_usd"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No party packages found."

        lines = ["Party packages:"]
        for row in rows:
            location = row.get("locations", {}).get("name") if row.get("locations") else "All Locations"
            if location_name and location_name.lower() not in (location or "").lower():
                continue
            
            perks: List[str] = []
            if row.get("includes_food"):
                perks.append("food")
            if row.get("includes_drinks"):
                perks.append("drinks")
            if row.get("includes_decor"):
                perks.append("decor")
            perk_text = f" Includes {', '.join(perks)}." if perks else ""
            
            inclusions = row.get("package_inclusions") or []
            inclusion_items = [f"{i['item_name']} x{i.get('quantity', 1)}" for i in inclusions]
            inclusion_text = f" Inclusions: {', '.join(inclusion_items)}." if inclusion_items else ""
            
            lines.append(
                f"- {location}: {row['name']} - ${row['price_usd']:.2f} for {row['base_children']} kids, "
                f"{row['base_room_hours']}h.{perk_text}{inclusion_text}"
            )
        
        if len(lines) == 1:
            return "No party packages found for that location."
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing party packages: {e}"


@function_tool
def get_party_availability(
    start_datetime: str,
    end_datetime: str,
    location_name: str = "",
) -> str:
    """
    Show booked party room slots within a window to help gauge availability.
    """
    try:
        start = datetime.fromisoformat(start_datetime)
        end = datetime.fromisoformat(end_datetime)
    except ValueError:
        return "Invalid datetime. Use ISO format like 2025-01-15T14:00."
    if end <= start:
        return "end_datetime must be after start_datetime."

    try:
        endpoint = f"party_bookings?select=scheduled_start,scheduled_end,status,resources(name,locations(name))&status=in.(Pending,Confirmed)&scheduled_start=lt.{end.isoformat()}&scheduled_end=gt.{start.isoformat()}&order=scheduled_start"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No existing bookings; all rooms appear open in that window."

        lines = ["Booked party slots in that window:"]
        for row in rows:
            resource = row.get("resources") or {}
            room_name = resource.get("name", "Unknown Room")
            loc = resource.get("locations", {}).get("name") if resource.get("locations") else "Unknown"
            
            if location_name and location_name.lower() not in (loc or "").lower():
                continue
            
            booked_start = datetime.fromisoformat(row["scheduled_start"].replace("Z", "+00:00"))
            booked_end = datetime.fromisoformat(row["scheduled_end"].replace("Z", "+00:00"))
            
            lines.append(
                f"- {loc} - {room_name} booked {booked_start:%Y-%m-%d %H:%M} "
                f"to {booked_end:%H:%M} ({row['status']})"
            )
        
        if len(lines) == 1:
            return "No existing bookings for that location; all rooms appear open in that window."
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking party availability: {e}"


@function_tool
def create_party_booking(
    customer_id: int,
    package_id: int,
    resource_id: int,
    scheduled_start: str,
    scheduled_end: str,
    additional_kids: int = 0,
    additional_guests: int = 0,
    special_requests: str = "",
    status: str = "Pending",
) -> str:
    """
    Create a new party booking record.
    """
    if additional_kids < 0 or additional_guests < 0:
        return "additional_kids and additional_guests must be zero or greater."

    normalized_status = _normalize_choice(status, PARTY_STATUSES)
    if not normalized_status:
        return "Status must be one of: " + ", ".join(PARTY_STATUSES)

    try:
        start_dt = datetime.fromisoformat(scheduled_start)
        end_dt = datetime.fromisoformat(scheduled_end)
    except ValueError:
        return "Invalid datetime format. Use ISO format, e.g., 2025-11-03T12:00."
    if end_dt <= start_dt:
        return "scheduled_end must be after scheduled_start."

    try:
        # Check customer exists
        customer = db.get_by_id("customers", "customer_id", customer_id)
        if not customer:
            return "Customer not found. Please create a customer profile first."

        # Check room availability
        endpoint = f"party_bookings?select=booking_id&resource_id=eq.{resource_id}&status=in.(Pending,Confirmed)&scheduled_start=lt.{end_dt.isoformat()}&scheduled_end=gt.{start_dt.isoformat()}&limit=1"
        conflicts = db._make_request("GET", endpoint)
        if conflicts:
            return "That room is already booked during the requested time."

        data = {
            "package_id": package_id,
            "resource_id": resource_id,
            "customer_id": customer_id,
            "scheduled_start": start_dt.isoformat(),
            "scheduled_end": end_dt.isoformat(),
            "status": normalized_status,
            "additional_kids": additional_kids,
            "additional_guests": additional_guests,
            "special_requests": special_requests.strip() or None,
        }
        
        result = db.insert("party_bookings", data)
        if result and len(result) > 0:
            booking_id = result[0].get("booking_id")
            return (
                f"Created party booking #{booking_id} from {start_dt:%Y-%m-%d %H:%M} "
                f"to {end_dt:%Y-%m-%d %H:%M} with status {normalized_status}."
            )
        return "Failed to create party booking."
    except Exception as e:
        return f"Error creating party booking: {e}"


@function_tool
def update_party_booking(
    booking_id: int,
    status: str = "",
    scheduled_start: str = "",
    scheduled_end: str = "",
    additional_kids: Optional[int] = None,
    additional_guests: Optional[int] = None,
    special_requests: Optional[str] = None,
    reschedule_reason: str = "",
) -> str:
    """
    Update fields on an existing party booking. Provide at least one field to change.
    """
    try:
        # Get current booking
        booking = db.get_by_id("party_bookings", "booking_id", booking_id)
        if not booking:
            return "Booking not found."

        resource_id = booking["resource_id"]
        current_start = datetime.fromisoformat(booking["scheduled_start"].replace("Z", "+00:00"))
        current_end = datetime.fromisoformat(booking["scheduled_end"].replace("Z", "+00:00"))
        current_status = booking["status"]

        updates = {}

        if status:
            normalized_status = _normalize_choice(status, PARTY_STATUSES)
            if not normalized_status:
                return "Status must be one of: " + ", ".join(PARTY_STATUSES)
            updates["status"] = normalized_status
        else:
            normalized_status = current_status

        new_start_dt = None
        new_end_dt = None

        if scheduled_start:
            try:
                new_start_dt = datetime.fromisoformat(scheduled_start)
            except ValueError:
                return "Invalid scheduled_start datetime format."

        if scheduled_end:
            try:
                new_end_dt = datetime.fromisoformat(scheduled_end)
            except ValueError:
                return "Invalid scheduled_end datetime format."

        final_start = new_start_dt or current_start
        final_end = new_end_dt or current_end
        if final_end <= final_start:
            return "scheduled_end must be after scheduled_start."

        schedule_changed = (new_start_dt is not None) or (new_end_dt is not None)
        if schedule_changed:
            updates["scheduled_start"] = final_start.isoformat()
            updates["scheduled_end"] = final_end.isoformat()

            # Check for conflicts
            endpoint = f"party_bookings?select=booking_id&resource_id=eq.{resource_id}&booking_id=neq.{booking_id}&status=in.(Pending,Confirmed)&scheduled_start=lt.{final_end.isoformat()}&scheduled_end=gt.{final_start.isoformat()}&limit=1"
            conflicts = db._make_request("GET", endpoint)
            if conflicts:
                return "That room is already booked during the requested time."

        if additional_kids is not None:
            if additional_kids < 0:
                return "additional_kids must be zero or greater."
            updates["additional_kids"] = additional_kids

        if additional_guests is not None:
            if additional_guests < 0:
                return "additional_guests must be zero or greater."
            updates["additional_guests"] = additional_guests

        if special_requests is not None:
            updates["special_requests"] = special_requests.strip() or None

        if not updates:
            return "No updates were provided."

        db.update("party_bookings", "booking_id", booking_id, updates)

        # Record reschedule if schedule changed
        if schedule_changed and (final_start != current_start or final_end != current_end):
            reschedule_data = {
                "booking_id": booking_id,
                "old_start": current_start.isoformat(),
                "old_end": current_end.isoformat(),
                "new_start": final_start.isoformat(),
                "new_end": final_end.isoformat(),
                "reason": reschedule_reason.strip() or None,
            }
            db.insert("party_reschedules", reschedule_data)

        response = f"Updated party booking #{booking_id}. Current status: {normalized_status}."
        if schedule_changed:
            response += f" New schedule: {final_start:%Y-%m-%d %H:%M} to {final_end:%Y-%m-%d %H:%M}."
        return response
    except Exception as e:
        return f"Error updating party booking: {e}"


@function_tool
def get_store_policies(topic: str = "") -> str:
    """
    Retrieve active policy notes, optionally filtered by a keyword.
    """
    try:
        endpoint = "policies?select=key,value&is_active=eq.true&order=key"
        
        if topic:
            endpoint += f"&or=(key.ilike.*{topic}*,value.ilike.*{topic}*)"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No active policies found for that topic."

        return "\n".join(f"- {row['key']}: {row['value']}" for row in rows)
    except Exception as e:
        return f"Error getting store policies: {e}"


@function_tool
def list_store_locations(only_active: bool = True) -> str:
    """
    List store locations and their contact details.
    """
    try:
        endpoint = "locations?select=location_id,name,address_line,city,state,postal_code,country,phone,email,is_active&order=name"
        
        if only_active:
            endpoint += "&is_active=eq.true"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No locations found."

        lines = ["Store locations:"]
        for row in rows:
            status = "Active" if row.get("is_active") else "Inactive"
            address_parts = [part for part in [row.get("address_line"), row.get("city"), row.get("state"), row.get("postal_code")] if part]
            address_str = ", ".join(address_parts)
            lines.append(
                f"- #{row['location_id']} {row['name']} ({status}) – {address_str or 'Address not set'}; "
                f"Phone: {row.get('phone') or 'N/A'}; Email: {row.get('email') or 'N/A'}; Country: {row.get('country') or 'N/A'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing store locations: {e}"


@function_tool
def search_orders(status: str = "", customer_name: str = "", limit: int = 5) -> str:
    """
    Search orders by status or customer name.
    """
    limit = max(1, min(limit, 20))
    
    try:
        endpoint = f"orders?select=order_id,order_type,status,total_usd,created_at,customers(full_name)&order=created_at.desc&limit={limit}"
        
        if status:
            endpoint += f"&status=ilike.{status}"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No orders matched those filters."

        # Filter by customer name if provided (client-side filter due to join complexity)
        if customer_name:
            rows = [r for r in rows if r.get("customers") and customer_name.lower() in r["customers"].get("full_name", "").lower()]

        if not rows:
            return "No orders matched those filters."

        lines = ["Matching orders:"]
        for row in rows:
            customer = row.get("customers", {}).get("full_name") if row.get("customers") else "Guest"
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            lines.append(
                f"- #{row['order_id']} {customer} - {row['order_type']} {row['status']} "
                f"(${row['total_usd']:.2f}) created {created:%Y-%m-%d}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching orders: {e}"


@function_tool
def list_customer_orders(customer_id: int, limit: int = 5) -> str:
    """
    List recent orders for a specific customer.
    """
    limit = max(1, min(limit, 20))
    
    try:
        endpoint = f"orders?select=order_id,order_type,status,total_usd,created_at&customer_id=eq.{customer_id}&order=created_at.desc&limit={limit}"
        
        rows = db._make_request("GET", endpoint)
        
        if not rows:
            return "No orders found for that customer."

        lines = [f"Recent orders for customer #{customer_id}:"]
        for row in rows:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            lines.append(
                f"- #{row['order_id']} {row['order_type']} {row['status']} - ${row['total_usd']:.2f} on "
                f"{created:%Y-%m-%d}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing customer orders: {e}"


@function_tool
def get_order_details(order_id: int) -> str:
    """
    Provide a detailed view of an order, including items, payments, and refunds.
    """
    try:
        # Get order with customer and location
        endpoint = f"orders?select=*,customers(full_name,email),locations(name)&order_id=eq.{order_id}"
        order_rows = db._make_request("GET", endpoint)
        
        if not order_rows:
            return "Order not found."

        order = order_rows[0]
        customer = order.get("customers") or {}
        location = order.get("locations") or {}

        customer_name = customer.get("full_name", "Guest")
        customer_email = customer.get("email", "")
        location_name = location.get("name", "All Locations")

        customer_line = f"Customer: {customer_name}"
        if customer_email:
            customer_line += f" ({customer_email})"

        created_at = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(order["updated_at"].replace("Z", "+00:00"))

        lines = [
            f"Order #{order_id} ({order['order_type']}) - {order['status']}",
            customer_line,
            f"Location: {location_name}",
            (
                "Totals: "
                f"subtotal ${order['subtotal_usd']:.2f}, discount ${order['discount_usd']:.2f}, "
                f"tax ${order['tax_usd']:.2f}, total ${order['total_usd']:.2f}"
            ),
            f"Created: {created_at:%Y-%m-%d %H:%M}",
            f"Updated: {updated_at:%Y-%m-%d %H:%M}",
        ]
        if order.get("notes"):
            lines.append(f"Notes:\n{order['notes'].strip()}")

        # Get order items
        items_endpoint = f"order_items?select=item_type,name_override,quantity,unit_price_usd,line_total_usd,products(product_name),ticket_types(name)&order_id=eq.{order_id}&order=order_item_id"
        items = db._make_request("GET", items_endpoint)
        
        if items:
            lines.append("\nItems:")
            for item in items:
                if item.get("name_override"):
                    display_name = item["name_override"]
                elif item["item_type"] == "Product" and item.get("products"):
                    display_name = item["products"]["product_name"]
                elif item["item_type"] == "Ticket" and item.get("ticket_types"):
                    display_name = item["ticket_types"]["name"]
                else:
                    display_name = "Line item"
                
                lines.append(
                    f"- {display_name} ({item['item_type']}) x{item['quantity']} @ ${item['unit_price_usd']:.2f} "
                    f"= ${item['line_total_usd']:.2f}"
                )

        # Get payments
        payments_endpoint = f"payments?select=payment_id,provider,status,amount_usd,created_at&order_id=eq.{order_id}&order=created_at.desc"
        payments = db._make_request("GET", payments_endpoint)
        
        if payments:
            lines.append("\nPayments:")
            for payment in payments:
                created = datetime.fromisoformat(payment["created_at"].replace("Z", "+00:00"))
                lines.append(
                    f"- Payment #{payment['payment_id']} via {payment['provider']} {payment['status']} "
                    f"for ${payment['amount_usd']:.2f} on {created:%Y-%m-%d}"
                )

        # Get refunds
        refunds_endpoint = f"refunds?select=refund_id,status,amount_usd,created_at,reason&order_id=eq.{order_id}&order=created_at.desc"
        refunds = db._make_request("GET", refunds_endpoint)
        
        if refunds:
            lines.append("\nRefunds:")
            for refund in refunds:
                created = datetime.fromisoformat(refund["created_at"].replace("Z", "+00:00"))
                reason_text = f" ({refund['reason']})" if refund.get("reason") else ""
                lines.append(
                    f"- Refund #{refund['refund_id']} {refund['status']} for ${refund['amount_usd']:.2f} "
                    f"on {created:%Y-%m-%d}{reason_text}"
                )

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting order details: {e}"


@function_tool
def update_order_status(order_id: int, new_status: str, note: str = "") -> str:
    """
    Update the status of an order, optionally appending a note.
    """
    normalized = _normalize_choice(new_status, ORDER_STATUSES)
    if not normalized:
        return "Status must be one of: " + ", ".join(ORDER_STATUSES)

    try:
        # Get existing order
        order = db.get_by_id("orders", "order_id", order_id)
        if not order:
            return "Order not found."

        updates = {
            "status": normalized,
            "updated_at": datetime.now().isoformat(),
        }
        
        if note.strip():
            existing_notes = order.get("notes") or ""
            note_entry = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note.strip()}"
            updates["notes"] = existing_notes + note_entry

        db.update("orders", "order_id", order_id, updates)
        return f"Updated order {order_id} to {normalized}."
    except Exception as e:
        return f"Error updating order status: {e}"


@function_tool
def add_order_item(
    order_id: int,
    item_type: str,
    reference_id: int,
    quantity: int,
    unit_price_usd: float,
    name_override: str = "",
) -> str:
    """
    Add a new line item to an existing order and refresh totals.
    """
    normalized_type = _normalize_choice(item_type, ITEM_TYPES)
    if not normalized_type:
        return "Item type must be one of: " + ", ".join(ITEM_TYPES)
    if quantity <= 0:
        return "Quantity must be greater than zero."
    if unit_price_usd < 0:
        return "Unit price must be zero or greater."

    try:
        order = db.get_by_id("orders", "order_id", order_id)
        if not order:
            return "Order not found."

        subtotal = float(order.get("subtotal_usd") or 0)
        discount = float(order.get("discount_usd") or 0)
        tax = float(order.get("tax_usd") or 0)
        line_total = round(quantity * unit_price_usd, 2)

        item_data = {
            "order_id": order_id,
            "item_type": normalized_type,
            "product_id": reference_id if normalized_type == "Product" else None,
            "ticket_type_id": reference_id if normalized_type == "Ticket" else None,
            "booking_id": reference_id if normalized_type == "Party" else None,
            "name_override": name_override.strip() or None,
            "quantity": quantity,
            "unit_price_usd": unit_price_usd,
            "line_total_usd": line_total,
        }
        
        db.insert("order_items", item_data)

        new_subtotal = subtotal + line_total
        new_total = new_subtotal - discount + tax

        db.update("orders", "order_id", order_id, {
            "subtotal_usd": new_subtotal,
            "total_usd": new_total,
            "updated_at": datetime.now().isoformat(),
        })

        return (
            f"Added {quantity} x {normalized_type} item to order {order_id}; "
            f"new total ${new_total:.2f}."
        )
    except Exception as e:
        return f"Error adding order item: {e}"


@function_tool
def create_order_with_item(
    customer_id: int,
    item_type: str,
    reference_id: int,
    quantity: int,
    unit_price_usd: float,
    location_id: Optional[int] = None,
    note: str = "",
    name_override: str = "",
) -> str:
    """
    Create a new order for a single line item (toy, ticket, or party booking).
    """
    normalized_type = _normalize_choice(item_type, ITEM_TYPES)
    if not normalized_type:
        return "Item type must be one of: " + ", ".join(ITEM_TYPES)
    if quantity <= 0:
        return "Quantity must be greater than zero."
    if unit_price_usd < 0:
        return "Unit price must be zero or greater."

    order_type_map = {
        "Product": "Retail",
        "Ticket": "Admission",
        "Party": "Party",
    }
    order_type = order_type_map[normalized_type]
    line_total = round(quantity * unit_price_usd, 2)

    try:
        # Check customer exists
        customer = db.get_by_id("customers", "customer_id", customer_id)
        if not customer:
            return "Customer not found. Please create a customer profile before creating an order."

        order_data = {
            "customer_id": customer_id,
            "location_id": location_id,
            "order_type": order_type,
            "status": "Pending",
            "subtotal_usd": line_total,
            "discount_usd": 0,
            "tax_usd": 0,
            "total_usd": line_total,
            "notes": note.strip() or None,
        }
        
        order_result = db.insert("orders", order_data)
        if not order_result or len(order_result) == 0:
            return "Failed to create order."
        
        order_id = order_result[0]["order_id"]

        item_data = {
            "order_id": order_id,
            "item_type": normalized_type,
            "product_id": reference_id if normalized_type == "Product" else None,
            "ticket_type_id": reference_id if normalized_type == "Ticket" else None,
            "booking_id": reference_id if normalized_type == "Party" else None,
            "name_override": name_override.strip() or None,
            "quantity": quantity,
            "unit_price_usd": unit_price_usd,
            "line_total_usd": line_total,
        }
        
        db.insert("order_items", item_data)

        return f"Created order {order_id} ({order_type}) totaling ${line_total:.2f}."
    except Exception as e:
        return f"Error creating order: {e}"


@function_tool
def record_payment(
    order_id: int,
    provider: str,
    amount_usd: float,
    provider_payment_id: str = "",
    payment_status: str = "Captured",
) -> str:
    """
    Record a payment attempt for an order.
    """
    if amount_usd <= 0:
        return "Amount must be greater than zero."
    normalized_status = _normalize_choice(payment_status, PAYMENT_STATUSES)
    if not normalized_status:
        return "Payment status must be one of: " + ", ".join(PAYMENT_STATUSES)

    try:
        order = db.get_by_id("orders", "order_id", order_id)
        if not order:
            return "Order not found."

        payment_data = {
            "order_id": order_id,
            "provider": provider.strip() or "Manual",
            "provider_payment_id": provider_payment_id.strip() or None,
            "status": normalized_status,
            "amount_usd": amount_usd,
        }
        
        result = db.insert("payments", payment_data)
        if result and len(result) > 0:
            payment_id = result[0]["payment_id"]
            return (
                f"Recorded payment {payment_id} ({normalized_status}) for order {order_id} "
                f"in the amount of ${amount_usd:.2f}."
            )
        return "Failed to record payment."
    except Exception as e:
        return f"Error recording payment: {e}"


@function_tool
def create_refund(
    order_id: int,
    amount_usd: float,
    reason: str = "",
    payment_id: Optional[int] = None,
) -> str:
    """
    Create a refund record linked to an order (and optional payment).
    """
    if amount_usd <= 0:
        return "Refund amount must be greater than zero."

    try:
        order = db.get_by_id("orders", "order_id", order_id)
        if not order:
            return "Order not found."

        if payment_id is not None:
            endpoint = f"payments?select=payment_id&payment_id=eq.{payment_id}&order_id=eq.{order_id}"
            payment = db._make_request("GET", endpoint)
            if not payment:
                return "Payment not found for this order."

        refund_data = {
            "payment_id": payment_id,
            "order_id": order_id,
            "status": "Pending",
            "reason": reason.strip() or None,
            "amount_usd": amount_usd,
        }
        
        result = db.insert("refunds", refund_data)
        if result and len(result) > 0:
            refund_id = result[0]["refund_id"]
            return (
                f"Created refund {refund_id} for order {order_id} in the amount of "
                f"${amount_usd:.2f}."
            )
        return "Failed to create refund."
    except Exception as e:
        return f"Error creating refund: {e}"
