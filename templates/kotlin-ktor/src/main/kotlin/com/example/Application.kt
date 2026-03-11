package com.example

import com.fasterxml.jackson.databind.SerializationFeature
import com.zaxxer.hikari.HikariConfig
import com.zaxxer.hikari.HikariDataSource
import io.ktor.http.*
import io.ktor.serialization.jackson.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.SqlExpressionBuilder.eq
import org.jetbrains.exposed.sql.javatime.datetime
import org.jetbrains.exposed.sql.transactions.transaction
import java.time.LocalDateTime

object Items : Table("items") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255)
    val description = text("description").nullable()
    val createdAt = datetime("created_at").clientDefault { LocalDateTime.now() }
    override val primaryKey = PrimaryKey(id)
}

data class Item(val id: Int, val name: String, val description: String?, val createdAt: String)
data class ItemBody(val name: String?, val description: String?)

fun rowToItem(row: ResultRow) = Item(
    id = row[Items.id],
    name = row[Items.name],
    description = row[Items.description],
    createdAt = row[Items.createdAt].toString()
)

fun main() {
    val dbUrl = System.getenv("DATABASE_URL") ?: "jdbc:postgresql://localhost:5432/itemsdb"
    val dbUser = System.getenv("DATABASE_USER") ?: "postgres"
    val dbPass = System.getenv("DATABASE_PASSWORD") ?: "postgres"

    val config = HikariConfig().apply {
        jdbcUrl = dbUrl
        username = dbUser
        password = dbPass
        maximumPoolSize = 5
    }
    val dataSource = HikariDataSource(config)
    Database.connect(dataSource)

    transaction {
        SchemaUtils.create(Items)
    }

    embeddedServer(Netty, port = 8080) {
        install(ContentNegotiation) {
            jackson {
                disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            }
        }
        routing {
            get("/health") { call.respond(mapOf("status" to "ok")) }

            get("/items") {
                val items = transaction { Items.selectAll().map(::rowToItem) }
                call.respond(items)
            }

            post("/items") {
                val body = call.receive<ItemBody>()
                if (body.name.isNullOrBlank()) {
                    call.respond(HttpStatusCode.BadRequest, mapOf("error" to "name is required"))
                    return@post
                }
                val item = transaction {
                    val newId = Items.insert {
                        it[name] = body.name
                        it[description] = body.description
                    } get Items.id
                    Items.selectAll().where { Items.id eq newId }.single().let(::rowToItem)
                }
                call.respond(HttpStatusCode.Created, item)
            }

            get("/items/{id}") {
                val id = call.parameters["id"]?.toIntOrNull()
                    ?: return@get call.respond(HttpStatusCode.BadRequest)
                val item = transaction {
                    Items.selectAll().where { Items.id eq id }.firstOrNull()?.let(::rowToItem)
                }
                if (item == null) call.respond(HttpStatusCode.NotFound, mapOf("error" to "not found"))
                else call.respond(item)
            }

            put("/items/{id}") {
                val id = call.parameters["id"]?.toIntOrNull()
                    ?: return@put call.respond(HttpStatusCode.BadRequest)
                val body = call.receive<ItemBody>()
                val updated = transaction {
                    val count = Items.update({ Items.id eq id }) {
                        if (body.name != null) it[name] = body.name
                        if (body.description != null) it[description] = body.description
                    }
                    if (count == 0) null
                    else Items.selectAll().where { Items.id eq id }.first().let(::rowToItem)
                }
                if (updated == null) call.respond(HttpStatusCode.NotFound, mapOf("error" to "not found"))
                else call.respond(updated)
            }

            delete("/items/{id}") {
                val id = call.parameters["id"]?.toIntOrNull()
                    ?: return@delete call.respond(HttpStatusCode.BadRequest)
                val count = transaction { Items.deleteWhere { Items.id eq id } }
                if (count == 0) call.respond(HttpStatusCode.NotFound, mapOf("error" to "not found"))
                else call.respond(HttpStatusCode.NoContent)
            }
        }
    }.start(wait = true)
}
