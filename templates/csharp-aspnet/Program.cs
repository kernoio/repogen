using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddDbContext<AppDbContext>(opts =>
    opts.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));

var app = builder.Build();

// Auto-migrate on startup
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    db.Database.EnsureCreated();
}

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet("/items", async (AppDbContext db) =>
    await db.Items.ToListAsync());

app.MapPost("/items", async (AppDbContext db, ItemBody body) =>
{
    if (string.IsNullOrWhiteSpace(body.Name))
        return Results.BadRequest(new { error = "name is required" });
    var item = new Item { Name = body.Name, Description = body.Description };
    db.Items.Add(item);
    await db.SaveChangesAsync();
    return Results.Created($"/items/{item.Id}", item);
});

app.MapGet("/items/{id}", async (AppDbContext db, int id) =>
    await db.Items.FindAsync(id) is Item item
        ? Results.Ok(item)
        : Results.NotFound(new { error = "not found" }));

app.MapPut("/items/{id}", async (AppDbContext db, int id, ItemBody body) =>
{
    var item = await db.Items.FindAsync(id);
    if (item is null) return Results.NotFound(new { error = "not found" });
    item.Name = body.Name ?? item.Name;
    item.Description = body.Description ?? item.Description;
    await db.SaveChangesAsync();
    return Results.Ok(item);
});

app.MapDelete("/items/{id}", async (AppDbContext db, int id) =>
{
    var item = await db.Items.FindAsync(id);
    if (item is null) return Results.NotFound(new { error = "not found" });
    db.Items.Remove(item);
    await db.SaveChangesAsync();
    return Results.NoContent();
});

app.Run();

// ── Models ──────────────────────────────────────────────────────────────────

public class Item
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string? Description { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public record ItemBody(string? Name, string? Description);

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> opts) : base(opts) {}
    public DbSet<Item> Items => Set<Item>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Item>().ToTable("items");
        b.Entity<Item>().Property(i => i.Id).HasColumnName("id");
        b.Entity<Item>().Property(i => i.Name).HasColumnName("name").HasMaxLength(255).IsRequired();
        b.Entity<Item>().Property(i => i.Description).HasColumnName("description");
        b.Entity<Item>().Property(i => i.CreatedAt).HasColumnName("created_at")
            .HasDefaultValueSql("NOW()").ValueGeneratedOnAdd();
    }
}
