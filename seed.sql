INSERT INTO customers (name, email, phone) VALUES
    ('Seed Guest', 'seed@example.com', '+91-9000000000');

INSERT INTO dining_tables (label, seats, active) VALUES
    ('T1', 2, 1),
    ('T2', 4, 1),
    ('T3', 6, 0);

INSERT INTO menu_categories (name, sort_order) VALUES
    ('Starters', 10),
    ('Mains', 20),
    ('Drinks', 30);

INSERT INTO menu_items (category_id, name, description, price_cents, available) VALUES
    (1, 'Tomato Soup', 'Roasted tomato soup', 450, 1),
    (2, 'Paneer Tikka', 'Charred paneer with peppers', 850, 1),
    (3, 'Lime Soda', 'Fresh lime soda', 250, 1),
    (2, 'Chef Special', 'Seasonal special, currently unavailable', 1200, 0);
