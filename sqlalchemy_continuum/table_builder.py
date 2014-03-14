import sqlalchemy as sa


class TableBuilder(object):
    """
    TableBuilder handles the building of version tables based on parent
    table's structure and versioning configuration options.
    """
    def __init__(
        self,
        versioning_manager,
        parent_table,
        model=None
    ):
        self.manager = versioning_manager
        self.parent_table = parent_table
        self.model = model

    def option(self, name):
        try:
            return self.manager.option(self.model, name)
        except TypeError:
            return self.manager.options[name]

    @property
    def table_name(self):
        """
        Returns the version table name for current parent table.
        """
        return self.option('table_name') % self.parent_table.name

    @property
    def parent_columns(self):
        for column in self.parent_table.c:
            if (
                self.model and
                self.manager.is_excluded_column(self.model, column)
            ):
                continue
            if not self.model and column in self.manager.options['exclude']:
                continue
            yield column

    @property
    def reflected_columns(self):
        """
        Returns reflected parent table columns.

        All columns from parent table are reflected except those that:
        1. Are auto assigned date or datetime columns. Use include option
        parameter if you wish to have these included.
        2. Columns that are part of exclude option parameter.
        """
        columns = []

        transaction_column_name = self.option('transaction_column_name')

        for column in self.parent_columns:
            column_copy = self.reflect_column(column)
            columns.append(column_copy)

        # When using join table inheritance each table should have own
        # transaction column.
        if transaction_column_name not in [c.key for c in columns]:
            columns.append(sa.Column(transaction_column_name, sa.BigInteger))

        return columns

    def reflect_column(self, column):
        """
        Make a copy of parent table column and some alterations to it.

        :param column: SQLAlchemy Column object of parent table
        """
        # Make a copy of the column so that it does not point to wrong
        # table.
        column_copy = column.copy()
        # Remove unique constraints
        column_copy.unique = False
        # Remove onupdate triggers
        column_copy.onupdate = None
        if column_copy.autoincrement:
            column_copy.autoincrement = False
        if column_copy.name == self.option('transaction_column_name'):
            column_copy.nullable = False

        if not column_copy.primary_key:
            column_copy.nullable = True

        # Find the right column key
        if self.model is not None:
            for key, value in sa.inspect(self.model).columns.items():
                if value is column:
                    column_copy.key = key
        return column_copy

    @property
    def operation_type_column(self):
        """
        Return the operation type column. By default the name of this column
        is 'operation_type'.
        """
        return sa.Column(
            self.option('operation_type_column_name'),
            sa.SmallInteger,
            nullable=False,
            index=True
        )

    @property
    def transaction_column(self):
        """
        Returns transaction column. By default the name of this column is
        'transaction_id'.
        """
        return sa.Column(
            self.option('transaction_column_name'),
            sa.BigInteger,
            primary_key=True,
            index=True,
            autoincrement=False  # This is needed for MySQL
        )

    @property
    def end_transaction_column(self):
        """
        Returns end_transaction column. By default the name of this column is
        'end_transaction_id'.
        """
        return sa.Column(
            self.option('end_transaction_column_name'),
            sa.BigInteger,
            index=True
        )

    @property
    def columns(self):
        data = self.reflected_columns
        data.append(self.transaction_column)
        if self.option('strategy') == 'validity':
            data.append(self.end_transaction_column)
        data.append(self.operation_type_column)
        return data

    def __call__(self, extends=None):
        """
        Builds version table.
        """
        columns = self.columns if extends is None else []

        self.manager.plugins.after_build_version_table_columns(self, columns)
        return sa.schema.Table(
            extends.name if extends is not None else self.table_name,
            self.parent_table.metadata,
            *columns,
            extend_existing=extends is not None
        )
