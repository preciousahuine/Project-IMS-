1. Customer Statement of Requirements
A lot of small businesses still run their inventory out of a notebook or a spreadsheet someone started three years ago and never redesigned. It works until it doesn't. Nobody can say for sure how many units of something are left, sales staff and the storeroom are looking at different numbers, and reordering ends up being a guess based on whoever remembers to check.
IMS is my attempt to fix that for a business with a single location. It's a web app where product data, stock counts, sales, and purchases all live in one place instead of being split across a spreadsheet, a notebook, and someone's memory. A manager adds a product once; after that, selling it or restocking it just updates the same record, so the quantity on screen is the quantity actually on the shelf.
The people using it won't all need the same things. A sales associate just needs to log a sale and check what's in stock, not edit supplier pricing or manage accounts. A storekeeper needs to log incoming stock. An owner or manager wants the bigger picture: what's low, what's selling, what's worth reordering. IMS gives each of them a version of the app scoped to their job instead of one interface trying to do everything for everyone.
For this iteration I'm keeping the scope to one location: product management, stock tracking, accounts with roles, and the core reports. Multiple warehouses and anything that talks to outside systems (like a supplier's ordering API) are ideas for later, not part of this build.

2. Requirements Specification
2.1 Functional Requirements
These are the things the system has to actually do.
ID	Requirement
FR1	User Login: Users shall be able to create an account and log in with a username/email and password. 
FR2	Role Access: The system shall assign each user a role (Owner, Manager, Sales Personnel, Storekeeper/Warehouse Worker) that determines which features they can access. 
FR3	Product Addition: Managers and owners shall be able to add a new product with information like product name, product ID, price, quantity, category, and date received. 
FR4	Search Product: Users shall be able to search for a product by name, ID, and category. To update the product. 
FR5	Update Product: Authorized users shall be able to update a product's details (price, category, supplier, etc.).
FR6	Delete Product: Authorized users shall be able to delete or deactivate a product that is no longer sold.
FR7	The system shall automatically decrease a product's available quantity when a sale is recorded.
FR8	The system shall automatically increase a product's available quantity when new stock is received (a purchase/restock is recorded).
FR9	The system shall display a dashboard showing total number of products, total stock value, items running low, and items out of stock.
FR10	The system shall notify designated users when a product's quantity falls below a configurable reorder threshold.
FR11	The system shall generate reports on sales, purchases, current stock levels, and the products that sell best, filterable by date range.
FR12	Owners and Managers shall be able to view, create, and deactivate user accounts and assign roles.
FR13	Sales Personnel shall be able to record a sale and view current stock availability, without access to user management or supplier cost data.
FR14	Storekeepers/Warehouse Workers shall be able to record incoming and outgoing stock movements tied to a specific product.
FR15	The system shall keep a history log of stock changes (what changed, when, and by whom) for auditing.
2.2 Nonfunctional Requirements
These are less about what the system does and more about how well it has to do it.
ID	Requirement
NFR1	Performance: Common actions (search, add product, record a sale) shall return a result in under 2 seconds under normal load.
NFR2	Usability: The web interface shall be responsive and usable on desktop, tablet, and phone screen sizes.
NFR3	Security: Passwords shall be stored hashed (never in plain text), and access control based on user role shall be enforced on the server, not just hidden in the interface.
NFR4	Reliability: The system shall correctly maintain stock accuracy even when multiple users update the same product concurrently (no lost updates). 
NFR5	Availability: The application shall be available for use during normal business hours with minimal unplanned downtime. 
NFR6	Maintainability: Backend code shall be organized into clear modules (products, users, sales, reports) to simplify future changes. 
NFR7	Portability: The client shall run in any modern browser (Chrome, Edge, Firefox) without requiring code written for one browser in particular. 
NFR8	Scalability: The data model shall support at least 10,000 products and 100,000 transaction records without redesign. 
NFR9	Data Integrity: All inputs (e.g., price, quantity) shall be validated on both client and server to prevent invalid data, such as negative stock or a price that isn't a number. 
NFR10	Auditability: Every create, update, and delete action on inventory data shall be traceable to a user and timestamp. 

 3. Data and Storage Blueprint
3.1 Data Input
Most of what goes into IMS is typed in by a person, not pulled from somewhere else automatically:
•	Manual entry: this is the main one. A manager or storekeeper fills out a form to add a product: name, category, price, quantity, supplier, date received. Both the browser and the server check the values before anything gets saved.
•	Transactional entry: sales staff record a sale through a short form (product, quantity, timestamp); storekeepers do the same thing for incoming stock. It's still manual entry, just tied to a transaction instead of a product record.
•	Bulk import, later: a CSV upload so a business can dump their old spreadsheet in at once instead of retyping everything. I'm not building this for Iteration 1, but it's in the backlog below since it matters for real adoption.
•	Everything else the system "generates," like dashboard numbers, reports, and low stock flags, isn't really input at all. It's just math run over the entries above.
3.2 Database / Storage Solution
The Inventory Management System will use a MySQL relational database for permanent data storage.

The project is suitable for MySQL because the application contains various types of interrelated information. For example, a product can belong to a category, purchases can be associated with suppliers, and sales transactions can contain products.
