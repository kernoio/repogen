package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.Optional;

@RestController
public class ItemController {
    private final ItemRepository repo;

    public ItemController(ItemRepository repo) {
        this.repo = repo;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/items")
    public List<Item> list() {
        return repo.findAll();
    }

    @PostMapping("/items")
    public ResponseEntity<?> create(@RequestBody Map<String, String> body) {
        String name = body.get("name");
        if (name == null || name.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "name is required"));
        }
        Item item = new Item(name, body.get("description"));
        return ResponseEntity.status(HttpStatus.CREATED).body(repo.save(item));
    }

    @GetMapping("/items/{id}")
    public ResponseEntity<?> get(@PathVariable Long id) {
        Optional<Item> found = repo.findById(id);
        if (found.isEmpty()) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
        return ResponseEntity.ok(found.get());
    }

    @PutMapping("/items/{id}")
    public ResponseEntity<?> update(@PathVariable Long id, @RequestBody Map<String, String> body) {
        Optional<Item> found = repo.findById(id);
        if (found.isEmpty()) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
        Item item = found.get();
        if (body.containsKey("name")) item.setName(body.get("name"));
        if (body.containsKey("description")) item.setDescription(body.get("description"));
        return ResponseEntity.ok(repo.save(item));
    }

    @DeleteMapping("/items/{id}")
    public ResponseEntity<?> delete(@PathVariable Long id) {
        if (!repo.existsById(id)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "not found"));
        }
        repo.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
